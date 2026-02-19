import json
import logging
import re

import requests
from django.contrib.auth.models import update_last_login
from django.core.files import File
from django.http import JsonResponse
from django.http.response import Http404
from rest_framework import status
from rest_framework.generics import ListAPIView, DestroyAPIView, RetrieveAPIView, CreateAPIView
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_jwt.views import ObtainJSONWebToken
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from celery.result import AsyncResult

from profiles.tasks import run_visualization

from profiles.utils.flow_control import trigger_pause_signal
from profiles.models import Profile, JsonFile, TextFile
from profiles.serializers import *
from profiles.tasks import create_json, is_comment, is_info, get_lines_amount_for, create_community

MAX_CNF_SIZE = [100000, 100000]
logger = logging.getLogger('profiles')


def get_profile(user):
    return Profile.objects.get_or_create(user=user)[0]


class CurrentUserView(APIView):
    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)


class EditUserView(APIView):
    def put(self, request):
        user = request.user
        json_data = json.loads(request.body)

        user.email = json_data['email']
        user.set_password(json_data['password'])
        user.username = json_data['name']
        user.save()
        return Response(UserSerializer(user).data)


def start_community_task(request, visualization_id):
    try:
        existing_visualization = JsonFile.objects.get(pk=visualization_id)
        result = JsonFile.objects.create(
            text_file=TextFile.objects.get(id=existing_visualization.text_file_id),
            json_format='community',
            selected_vars=[]
        )
        status = result.status

        if status == 'empty':
            result.status = 'pending'
            result.save()

            json_task = create_community.delay(visualization_id, result.id)
            json_payload = {"message": "This task has been already proceeded", "status": "not ok",
                            'task_id': json_task.id}

            result.task_id = json_task.id
            result.json_format = "community"
            result.save()

        else:
            json_payload = {
                "message": "This task has been already proceeded",
                "status": "not ok"
            }
    except Exception as e:
        print(e)
        json_payload = {"message": "Something went wrong",
                        "status": "not ok"
                        }
    return JsonResponse(json_payload)


def start_task(request, format, text_file_id):
    json_payload = None
    try:
        json_payload = {
            "message": "The task had started",
            "status": "ok"
        }

        json_file, j_c = JsonFile.objects.get_or_create(
            text_file=TextFile.objects.get(id=text_file_id),
            json_format=format,
            selected_vars=[]
        )
        status = json_file.status

        if status == 'empty':
            json_task = create_json.delay(text_file_id, json_file.id, json_file.json_format, json_file.selected_vars)

            json_payload['task_id'] = json_task.id

            json_file.task_id = json_task.id
            json_file.save()
        else:
            json_payload = {
                "message": "This task has been already proceeded",
                "status": "not ok"
            }

    except Exception as e:
        print(e)
        json_payload = {"message": "Something went wrong",
                        "status": "not ok"
                        }

    finally:
        return JsonResponse(json_payload)


class VisualizationView(ListAPIView):
    serializer_class = JsonFileSerializer

    def get_queryset(self):
        current_user = self.request.user
        profile = get_profile(current_user)

        return JsonFile.objects.filter(text_file__profile=profile)


class RegistrationView(CreateAPIView):
    model = User
    permission_classes = (AllowAny,)
    serializer_class = UserSerializer

    def post(self, request):

        print(request.data)

        if not ('recaptcha' in request.data and 'username' in request.data and 'password' in request.data):
            return Response(status=401, data={request.data})

        user = User.objects.create_user(
            username=request.data['username'],
            password=request.data['password'],
            first_name=request.data['firstname'],
            last_name=request.data['lastname'],
            email=request.data['email']
        )
        user.save()

        # Temporary bypass recaptcha for quick testing:
        # recaptcha_result = requests.post(...).json()
        # recaptcha_response = request.data['recaptcha']

        # recaptcha_result = requests.post(
        #     "https://www.google.com/recaptcha/api/siteverify",
        #     data={
        #         'secret': "6LfyTO4ZAAAAAD_5_g6xXBv2D-JnRPdKESLqpScF",
        #         'response': recaptcha_response
        #     }
        # ).json().get("success",False)

        # Temporary bypass recaptcha for quick testing:
        recaptcha_result = {"success": True}  # Force True

        

        if not recaptcha_result:
            return Response(status=400)

        return Response(status=200)

@method_decorator(csrf_exempt, name='dispatch')
class SatFileUploadView(APIView):
    parser_classes = (MultiPartParser,)
    permission_classes = (AllowAny,)

    def put(self, request, filename):
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response(status=400)

        INFO_LINE_REGEX = re.compile(r'^p\s+cnf\s+[1-9]\d*\s+[1-9]\d*\s*$')
        COMMENT_LINE_REGEX = re.compile(r'^\s*c\b.*$', re.IGNORECASE)
        CNF_LINE_REGEX = re.compile(r'^\s*(-?[1-9]\d*\s+)*0\s*$')

        raw = file_obj.read().decode("utf-8", errors="ignore").splitlines()

        lines_amount = sum(
            1 for line in raw
            if not line.lstrip().startswith(('p', 'P', 'c', 'C')) and line.strip() != ''
        )

        success = True

        for idx, line in enumerate(raw):
            if idx == 0 and line.startswith("\ufeff"):
                line = line[1:]

            s = line.rstrip()

            if not s or s.isspace():
                success = False
                break

            if s.lstrip().lower().startswith("c"):
                if not COMMENT_LINE_REGEX.match(s):
                    success = False
                    break
                continue

            if s.lstrip().lower().startswith("p"):
                if not INFO_LINE_REGEX.match(s):
                    success = False
                    break
                parts = s.split()
                try:
                    declared = int(parts[3])
                except:
                    success = False
                    break
                if declared != lines_amount:
                    success = False
                    break
                continue

            if not CNF_LINE_REGEX.match(s):
                success = False
                break

        if not success:
            return Response(status=400)

        file_obj.seek(0)
        profile = get_profile(request.user)

        TextFile.objects.create(
            name=filename,
            profile=profile,
            content=file_obj,
            kind="sat"
        )

        return Response(status=204)


@method_decorator(csrf_exempt, name='dispatch')
class MaxSatFileUploadView(APIView):
    parser_classes = (MultiPartParser,)
    permission_classes = (AllowAny,)

    def put(self, request, filename):
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response(status=400)

        INFO_LINE_REGEX = re.compile(r'^p\s+cnf\s+[1-9]\d*\s+[1-9]\d*\s*$')
        COMMENT_LINE_REGEX = re.compile(r'^\s*c\b.*$', re.IGNORECASE)
        CNF_LINE_REGEX = re.compile(r'^\s*(-?[1-9]\d*\s+)*0\s*$')

        raw = file_obj.read().decode("utf-8", errors="ignore").splitlines()

        lines_amount = sum(
            1 for line in raw
            if not line.lstrip().startswith(('p', 'P', 'c', 'C')) and line.strip() != ''
        )

        success = True

        for idx, line in enumerate(raw):
            if idx == 0 and line.startswith("\ufeff"):
                line = line[1:]

            s = line.rstrip()

            if not s or s.isspace():
                success = False
                break

            if s.lstrip().lower().startswith("c"):
                if not COMMENT_LINE_REGEX.match(s):
                    success = False
                    break
                continue

            if s.lstrip().lower().startswith("p"):
                if not INFO_LINE_REGEX.match(s):
                    success = False
                    break
                parts = s.split()
                try:
                    declared = int(parts[3])
                except:
                    success = False
                    break
                if declared != lines_amount:
                    success = False
                    break
                continue

            if not CNF_LINE_REGEX.match(s):
                success = False
                break

        if not success:
            return Response(status=400)

        file_obj.seek(0)
        profile = get_profile(request.user)

        TextFile.objects.create(
            name=filename,
            profile=profile,
            content=file_obj,
            kind="maxsat"
        )

        return Response(status=204)

class TextSatFilesView(ListAPIView):
    serializer_class = TextFileSerializer

    def get_queryset(self):
        current_user = self.request.user
        profile = get_profile(current_user)
        return TextFile.objects.filter(profile=profile, kind='sat')


class TextMaxSatFilesView(ListAPIView):
    serializer_class = TextFileSerializer

    def get_queryset(self):
        current_user = self.request.user
        profile = get_profile(current_user)

        return TextFile.objects.filter(profile=profile, kind='maxsat')


class TextSatFileView(DestroyAPIView, RetrieveAPIView):
    queryset = TextFile.objects.all()
    serializer_class = TextFileSerializerDetail

    def delete(self, request, *args, pk=None, vistype=None, **kwargs):
        current_user = self.request.user
        profile = get_profile(current_user)
        try:
            text_file = TextFile.objects.get(pk=pk, profile=profile)
        except TextFile.DoesNotExist:
            raise Http404
        text_file.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TextMaxSatFileView(DestroyAPIView, RetrieveAPIView):
    queryset = TextFile.objects.all()
    serializer_class = TextFileSerializerDetail

    def delete(self, request, *args, pk=None, vistype=None, **kwargs):
        current_user = self.request.user
        profile = get_profile(current_user)
        try:
            text_file = TextFile.objects.get(pk=pk, profile=profile)
        except TextFile.DoesNotExist:
            raise Http404
        text_file.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class JsonFileView(DestroyAPIView, RetrieveAPIView):
    queryset = JsonFile.objects.all()
    serializer_class = JsonFileSerializerDetail

    def delete(self, request, *args, pk=None, vistype=None, **kwargs):
        current_user = self.request.user
        profile = get_profile(current_user)
        try:
            json_file = JsonFile.objects.get(id=pk)
            json_file.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except JsonFile.DoesNotExist:
            raise Http404


from django.contrib.auth.models import User
from django.contrib.auth.models import update_last_login
from rest_framework_jwt.views import ObtainJSONWebToken
from rest_framework.response import Response
import requests

class ObtainLoginTokenView(ObtainJSONWebToken):
    def post(self, request):
        if not all(k in request.data for k in ('username', 'password')):
            return Response({'detail': 'Missing required fields'}, status=400)

        result = super().post(request)

        if result.status_code == 200:
            try:
                user = User.objects.get(username=request.data['username'])
                update_last_login(None, user)
            except User.DoesNotExist:
                pass

        return result
    
import json
from django.http import JsonResponse

def get_visualization_data(request, js_id, kind):
    try:
        obj = JsonFile.objects.get(id=js_id)
        data = obj.content

        # content jest stringiem → zamieniamy na dict
        return JsonResponse(json.loads(data), safe=False)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

@csrf_exempt
def pause_visualization(request, js_id):
    """
    Ustawia flagę w Redis, która spowoduje przerwanie taska przy najbliższej okazji.
    """
    try:
        # Wysyłamy sygnał do Redisa. Task (create_json) go wyłapie i rzuci wyjątek.
        trigger_pause_signal(js_id)
        return JsonResponse({'status': 'ok', 'message': 'Pause signal sent'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@csrf_exempt
def resume_visualization(request, js_id):
    """
    Wznawia zadanie, jeśli jest w stanie 'paused'.
    """
    try:
        json_file = JsonFile.objects.get(id=js_id)
        
        if json_file.status != 'paused':
            return JsonResponse({'status': 'error', 'message': 'Visualization is not paused'}, status=400)

        # Pobieramy parametry potrzebne do ponownego uruchomienia create_json.
        # create_json.delay(obj_id, js_id, js_format, selected_vars)
        # Zgodnie z Twoim start_task: obj_id to text_file.id
        
        text_file_id = json_file.text_file.id
        
        # Uruchamiamy taska ponownie. 
        # Backend sam wykryje status 'paused' w bazie i załaduje checkpoint.
        json_task = create_json.delay(
            text_file_id, 
            json_file.id, 
            json_file.json_format, 
            json_file.selected_vars
        )
        
        # Aktualizujemy ID taska (opcjonalne, ale dobra praktyka)
        json_file.task_id = json_task.id
        json_file.save()
        
        return JsonResponse({'status': 'ok', 'message': 'Visualization resumed'})
    except Exception as e:
        print(e)
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
