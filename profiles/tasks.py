import itertools
import logging
import queue
import re
import time
import uuid
from subprocess import Popen, PIPE
import os
import matplotlib.pyplot as plt
import numpy as np
from colormap import rgb2hex as rgb2hexColormap
from django.core.files import File
from igraph import *
import traceback
from formulavis.celeryconf import app
from formulavis.settings import SATELITE_PATH
from profiles.communities import CommunityManager
from profiles.email import EmailService
from profiles.models import JsonFile, TextFile, Profile
from profiles.vis_tasks import vis_2clause, vis_directed, vis_dpll, i_cdcl
from typing import List, Set, Tuple, Optional, Iterator
from profiles.vis_tasks.i_cdcl import CDCLSolver, Formula, Clause, Literal, made_tree, SemanticProfiler
from profiles.vis_tasks.i_dpll import DpllIteration
from profiles.vis_tasks.vis_dpll import DpllTree
from profiles.vis_tasks.heatmap_helpers import regrid_x, regrid_y
from profiles.utils.flow_control import PauseInterrupt, NumpyEncoder, check_interruption
from pysat.solvers import Glucose3
import random
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger('email_on_exception_logger')

import json

import ast

def restore_tuple_keys(d):
    """
    Konwertuje klucze słownika ze stringów z powrotem na krotki (tuples).
    JSON zapisuje klucz (1, 2) jako string "(1, 2)" lub "1, 2".
    Ta funkcja próbuje to naprawić bezpiecznie przy użyciu ast.literal_eval.
    """
    if not isinstance(d, dict):
        return d
        
    new_dict = {}
    for k, v in d.items():
        if isinstance(k, str):
            try:
                # Próbujemy zinterpretować string jako strukturę pythona
                # np. "(1, 2)" -> (1, 2)
                converted_key = ast.literal_eval(k)
                
                # Jeśli wynik to krotka, używamy jej jako klucza
                if isinstance(converted_key, tuple):
                    new_dict[converted_key] = v
                else:
                    new_dict[k] = v
            except (ValueError, SyntaxError):
                # Jeśli to zwykły string (np. "id_123"), zostawiamy jak jest
                new_dict[k] = v
        else:
            new_dict[k] = v
    return new_dict

@app.task(bind=True)
def create_json(self, obj_id, js_id, js_format, selected_vars):
    
    # 1. LOGIKA WZNAWIANIA (LOAD STATE)
    obj = JsonFile.objects.get(id=js_id)
    resume_state = None
    
    if obj.status == 'paused' and obj.content:
        try:
            # Próba wczytania checkpointa zapisanego w content
            resume_state = json.loads(obj.content)
            print(f"RESUMING task {js_id} from checkpoint...")
        except Exception as e:
            print(f"Failed to load checkpoint for {js_id}: {e}. Starting fresh.")
            resume_state = None
            
    # Ustawiamy z powrotem na pending, żeby UI pokazywało spinner/aktywność
    obj.status = 'pending'
    obj.save()

    now = time.time()

    # 2. PRZYGOTOWANIE DANYCH
    if isinstance(selected_vars, str):
        try:
            selected_vars = json.loads(selected_vars)
        except:
            selected_vars = []

    # Mapa funkcji
    formats = {
        'sat_vis_factor':        create_sat_vis_factor,
        'sat_vis_interaction':   create_sat_vis_interaction,
        'sat_vis_matrix':        create_sat_vis_matrix,
        'sat_vis_tree':          create_sat_vis_tree,
        'sat_vis_cluster':       create_sat_vis_cluster,
        'sat_vis_resolution':    create_sat_vis_resolution,
        'sat_vis_distribution':  create_sat_vis_distribution,
        'sat_vis_directed':      create_sat_vis_directed,
        'sat_vis_2clause':       create_sat_vis_2clause,
        'sat_vis_dpll':          create_sat_vis_dpll,
        'sat_vis_heatmap':       create_sat_vis_heatmap,
        'sat_vis_cdcl':          create_sat_vis_cdcl,
        'sat_vis_what_if':       create_sat_vis_what_if,
        'sat_vis_landscape':     create_sat_landscape,         
        'maxsat_vis_factor':     create_maxsat_vis_factor,
        'maxsat_vis_interaction':create_maxsat_vis_interaction,
        'maxsat_vis_matrix':     create_maxsat_vis_matrix,
        'maxsat_vis_tree':       create_maxsat_vis_tree,
        'maxsat_vis_cluster':    create_maxsat_vis_cluster,
        'maxsat_vis_resolution': create_maxsat_vis_resolution,

        'variables':             create_variables_list,
        'raw':                   create_raw,
    }

    task_func = formats.get(js_format)

    if task_func is None:
        obj.status = 'done'
        obj.content = json.dumps({'error': f'Unknown format: {js_format}'})
        obj.save()
        return

    # 3. WYKONANIE Z OBSŁUGĄ PAUZY (Try/Except)
    try:
        # UWAGA: Wywołujemy funkcję przekazując 'resume_state'.
        # Musisz zaktualizować definicje swoich funkcji (np. create_sat_vis_heatmap),
        # żeby przyjmowały ten argument (np. def func(..., resume_state=None)).
        task_func(obj_id, js_id, js_format, selected_vars, resume_state=resume_state)

    except PauseInterrupt as e:
        # === TUTAJ WPADAMY, GDY UPDATE_PROGRESS RZUCI WYJĄTEK ===
        print(f"Task {js_id} PAUSED by user interrupt.")
        
        # Pobieramy świeży obiekt z bazy
        obj = JsonFile.objects.get(id=js_id)
        
        # Serializujemy stan (używając NumpyEncoder dla macierzy)
        checkpoint_data = json.dumps(e.state_data, cls=NumpyEncoder)
        
        obj.content = checkpoint_data
        obj.status = 'paused'
        
        # Opcjonalnie: Ładny tekst postępu w GUI
        if obj.progress:
            percent = obj.progress.replace('Progress: ', '').replace('%', '')
            # Upewnij się, że percent to liczba, bo czasem może być śmieć
            try:
                obj.progress = f"Paused at {float(percent):.1f}%"
            except:
                obj.progress = "Paused"

        obj.save()
        
        # Kończymy task. Worker jest wolny. Nie wysyłamy maila.
        return "PAUSED"

    except Exception as e:
        # === OBSŁUGA KRYTYCZNYCH BŁĘDÓW ===
        print(f"Task {js_id} CRASHED: {e}")
        traceback.print_exc()
        
        obj = JsonFile.objects.get(id=js_id)
        obj.status = 'error'
        # Zapiszmy błąd jako JSON, żeby frontend mógł go wyświetlić
        obj.content = json.dumps({'error': str(e)})
        obj.save()
        return "ERROR"

    # 4. FINALIZACJA (SUKCES)
    # Jeśli doszliśmy tutaj, to nie było pauzy ani błędu.
    try:
        text_file = TextFile.objects.get(id=obj_id)
        user = text_file.profile.user
        visualization_name = text_file.name
        duration = int(time.time() - now)

        EmailService().send_email(
            user.email,
            f'ForVis Visualization {visualization_name}',
            f'ForVis visualization {visualization_name} finished in {duration} seconds.'
        )
    except Exception as email_err:
        print(f"Failed to send email: {email_err}")
        # Nie crashujemy taska, jeśli tylko mail nie poszedł
        pass

    return "DONE"



# @app.task()
# def create_community(visualization_id, result_id):
#     result = JsonFile.objects.get(pk=result_id)
#     visualization = JsonFile.objects.get(pk=visualization_id)
#     graph_dict = visualization.content
#     communities = CommunityManager(graph_dict, result).calculate_communities()

#     group = 0
#     for community in communities:
#         for vertex in community.vertex_list:
#             [x for x in graph_dict['nodes'] if x['id'] == vertex][0]['group'] = group
#         group += 1
#     for edge in graph_dict['edges']:
#         if 'color' in edge:
#             edge['color']['color'] = 'black'

#     result.content = json.dumps(graph_dict)
#     result.status = 'done'
#     result.progress = 'Progress: 100.0%'
#     result.save()

@app.task()
def create_community(visualization_id, result_id):
    visualization = JsonFile.objects.get(pk=visualization_id)
    result = JsonFile.objects.get(pk=result_id)

    # content jest teraz STRINGIEM — próbujemy zamienić go na dict
    raw_content = visualization.content

    try:
        if isinstance(raw_content, str):
            graph_dict = json.loads(raw_content)
        else:
            graph_dict = raw_content
    except Exception as e:
        # jeśli JSON źródłowy jest uszkodzony — zapisz błąd zamiast crasha
        result.content = json.dumps({
            "error": f"Invalid JSON in visualization: {e}"
        })
        result.status = "error"
        result.progress = "Progress: 100.0%"
        result.save()
        return

    # TERAZ graph_dict to już dict i CommunityManager może działać
    communities = CommunityManager(graph_dict, result).calculate_communities()

    # dodawanie community do nodes + color fix
    group = 0
    for community in communities:
        for vertex in community.vertex_list:
            for node in graph_dict.get('nodes', []):
                if node.get('id') == vertex:
                    node['group'] = group
        group += 1

    # defensywne odbarwienie edges
    for edge in graph_dict.get('edges', []):
        if isinstance(edge, dict) and 'color' in edge:
            try:
                edge['color']['color'] = 'black'
            except Exception:
                pass

    # zapis wyniku
    result.content = json.dumps(graph_dict)
    result.status = 'done'
    result.progress = 'Progress: 100.0%'
    result.save()


@app.task()
def create_sat_vis_heatmap(obj_id, js_id, js_format, selected_vars, resume_state=None):
    print("SAT_VIS_Heatmap")

    num_colors = 10
    obj = JsonFile.objects.get(id=js_id)

    if not resume_state:
        obj.status = 'pending'
        obj.save()

    data = {
        "info": None,
        "datasets": []
    }

    text_file = TextFile.objects.get(id=obj_id)

    # --- 1. INICJALIZACJA STANU ---
    var_count = None
    cl_count = None
    cl_dict = {}
    val_dict = {} # <--- DODANO INICJALIZACJĘ
    sat = None
    heatmap = None
    points = None
    
    stage = 'parsing'
    start_index = 0
    index_offset = 0

    if resume_state:
        print(f"Resuming SAT_VIS_HEATMAP from stage: {resume_state.get('stage')}")
        stage = resume_state.get('stage', 'parsing')
        start_index = resume_state.get('index', 0)
        data['info'] = resume_state.get('info_data')
        
        var_count = resume_state.get('var_count')
        cl_count = resume_state.get('cl_count')
        index_offset = resume_state.get('index_offset', 0)
        
        if stage == 'parsing':
            sat_list = resume_state.get('sat_list')
            if sat_list:
                sat = np.array(sat_list, dtype=np.int8)
            raw_cl = resume_state.get('cl_dict', {})
            cl_dict = {int(k): v for k, v in raw_cl.items()}
            
        elif stage == 'calculating':
            raw_cl = resume_state.get('cl_dict', {})
            cl_dict = {int(k): v for k, v in raw_cl.items()}
            
            # --- POPRAWKA: Odtwarzanie val_dict ---
            raw_val = resume_state.get('val_dict', {})
            val_dict = {int(k): v for k, v in raw_val.items()}
            # --------------------------------------
            
            hm_list = resume_state.get('heatmap_list')
            if hm_list:
                heatmap = np.array(hm_list)
                
        elif stage == 'processing_points':
            hm_list = resume_state.get('heatmap_list')
            if hm_list:
                heatmap = np.array(hm_list)
            points = resume_state.get('points')

    with open(text_file.content.path) as f:
        lines_amount = get_lines_amount_for(f)

    # --- FAZA 1: PARSOWANIE PLIKU ---
    if stage == 'parsing':
        with open(text_file.content.path) as f:
            text = File(f)
            f.seek(0)

            if start_index > 0:
                for _ in range(start_index):
                    next(f, None)

            for index, line in enumerate(f, start=start_index):
                
                if index % 200 == 0:
                    update_progress(index // 3, lines_amount, obj)
                    check_interruption(js_id, {
                        'stage': 'parsing',
                        'index': index,
                        'sat_list': sat,
                        'cl_dict': cl_dict,
                        'var_count': var_count,
                        'cl_count': cl_count,
                        'index_offset': index_offset,
                        'info_data': data.get('info')
                    })

                line = line.strip()
                if not line or line.startswith('c'):
                    index_offset += 1
                    continue
                if line.startswith('p'):
                    index_offset += 1
                    data['info'] = line.replace("\n", "").split(' ')
                    init_line = line.split()
                    if var_count is None:
                        var_count = int(init_line[2])
                        cl_count = int(init_line[3])
                        sat = np.zeros((cl_count, var_count), dtype=np.int8)
                    continue
                
                if sat is not None:
                    clause_vars = [int(i) for i in line.split() if i != '0']
                    clause_idx = index - index_offset
                    
                    if clause_idx < cl_count:
                        for variable in clause_vars:
                            if variable > 0:
                                sat[clause_idx][variable-1] = 1
                            else:
                                sat[clause_idx][-variable-1] = -1
                        cl_dict[clause_idx] = np.count_nonzero(sat[clause_idx])

        # Przejście parsing -> calculating
        stage = 'calculating'
        start_index = 0
        
        print(f"Formatting cnf DONE. var_count={var_count}, cl_count={cl_count}")
        
        # --- OBLICZAMY VAL_DICT PRZED CHECKPOINTEM ---
        if var_count is not None and sat is not None:
            val_dict = {i: np.count_nonzero(sat[:, i]) for i in range(var_count)}
        # ---------------------------------------------

        check_interruption(js_id, {
            'stage': 'calculating',
            'index': 0,
            # 'sat_list': sat, # Już nie potrzebujemy SAT w następnej fazie
            'cl_dict': cl_dict,
            'val_dict': val_dict, # <--- ZAPISUJEMY VAL_DICT
            'var_count': var_count,
            'cl_count': cl_count,
            'info_data': data.get('info')
        })

    # (Ten blok wykona się tylko jeśli nie wznowiliśmy w calculating, bo wtedy val_dict jest już wczytany)
    if not val_dict and var_count is not None and sat is not None:
        val_dict = {i: np.count_nonzero(sat[:, i]) for i in range(var_count)}
    print("Values Dict Creation DONE")

    if not cl_count or not var_count or cl_count == 0 or var_count == 0:
        print("No clauses or variables found.")
        obj.content = json.dumps({"error": "Empty or malformed file."})
        obj.status = 'done'
        obj.save()
        return obj

    if heatmap is None:
        heatmap = np.zeros([cl_count, var_count])

    if heatmap.size == 0:
        obj.content = json.dumps({"error": "Heatmap array empty."})
        obj.status = 'done'
        obj.save()
        return obj

    # --- FAZA 2: OBLICZANIE HEATMAPY ---
    if stage == 'calculating':
        for i in range(start_index, len(heatmap)):
            
            if i % 50 == 0:
                update_progress(lines_amount // 3 + i // 3, lines_amount, obj)
                check_interruption(js_id, {
                    'stage': 'calculating',
                    'index': i,
                    'heatmap_list': heatmap,
                    'cl_dict': cl_dict,
                    'val_dict': val_dict, # <--- ZAPISUJEMY TEŻ TUTAJ
                    'var_count': var_count,
                    'cl_count': cl_count,
                    'info_data': data.get('info')
                })

            val_ctr = -1
            for j in range(len(heatmap[i])):
                val_ctr += 1
                if cl_dict.get(i, 0) == 0:
                    heatmap[i][j] = 0
                else:
                    heatmap[i][j] = (val_dict.get(val_ctr, 0)/cl_dict.get(i, 1))
        
        print(f"Full Resolution Heatmap Creation DONE. heatmap shape: {heatmap.shape}")
        
        max_size = 500
        if heatmap.shape[0] > max_size:
            step_x = int(np.ceil(heatmap.shape[0]/max_size))
            heatmap = regrid_x(heatmap, step_x)
        if heatmap.shape[1] > max_size:
            step_y = int(np.ceil(heatmap.shape[1]/max_size))
            heatmap = regrid_y(heatmap, step_y)
        
        print(f"Scaling down DONE. heatmap shape: {heatmap.shape}")

        stage = 'processing_points'
        start_index = 0
        points = None
        
        check_interruption(js_id, {
            'stage': 'processing_points',
            'index': 0,
            'heatmap_list': heatmap,
            'info_data': data.get('info')
        })

    # --- PRZYGOTOWANIE KOLORÓW ---
    cmap = plt.get_cmap('inferno')
    
    if heatmap is None or heatmap.size == 0:
         return

    max_val = heatmap.max()*1.1
    step = max_val/num_colors
    ranges = []
    for clr in range(num_colors):
        ranges.append([clr*step, (clr+1)*step])
        
    color_list = [cmap(x/num_colors) for x in range(num_colors)]
    color_list_hex = [rgb2hexColormap(int(255*r), int(255*g), int(255*b)) for r, g, b, _ in color_list]
    
    if points is None:
        points = [[] for i in color_list]

    # --- FAZA 3: GENEROWANIE PUNKTÓW ---
    if stage == 'processing_points':
        for row_idx in range(start_index, len(heatmap)):
            
            if row_idx % 20 == 0:
                update_progress(2 * lines_amount // 3 + row_idx // 3, lines_amount, obj)
                check_interruption(js_id, {
                    'stage': 'processing_points',
                    'index': row_idx,
                    'heatmap_list': heatmap,
                    'points': points,
                    'info_data': data.get('info')
                })

            row = heatmap[row_idx]
            for el_idx, el in enumerate(row):
                entered = False
                for rng_index, rng in enumerate(ranges):
                    if rng[0] <= el < rng[1]:
                        points[rng_index].append({"x": row_idx, "y":el_idx})
                        entered = True
                if not entered:
                    points[0].append({"x": row_idx, "y": el_idx})

    update_progress(50, 100, obj)
    
    datasets = []
    for i in range(len(color_list_hex)):
        datasets.append({
            "label": str([np.round(ranges[i][0], 2), np.round(ranges[i][1], 2)]),
            "data": points[i],
            "backgroundColor": color_list_hex[i]
        })
        
    print("Vis Heatmap all DONE")
    obj.content = json.dumps({"datasets": datasets})
    obj.status = 'done'
    obj.progress = 'Progress: 100.0%'
    obj.save()
    return obj

@app.task()
def create_sat_vis_directed(obj_id, js_id, js_format, selected_vars, resume_state=None):
    print("SAT_VIS_DIRECTED_GRAPHICAL_MODEL", flush=True)
    obj = JsonFile.objects.get(id=js_id)

    if not resume_state:
        obj.status = 'pending'
        obj.save()

    data = {
        "info": None,
        "nodes": [],
        "edges": [],
        "options": vis_directed.options
    }

    nodes_tmp = {}
    edges_tmp = {}
    start_index = 0

    if resume_state:
        print(f"Resuming Directed Graph from line {resume_state.get('index')}")
        nodes_tmp = resume_state.get('nodes', {})
        nodes_tmp = {int(k): v for k, v in nodes_tmp.items()}
        edges_tmp = restore_tuple_keys(resume_state.get('edges', {}))
        start_index = resume_state.get('index', 0)
        data['info'] = resume_state.get('info_data')

    text_file = TextFile.objects.get(id=obj_id)
    
    last_check_time = time.time()

    try:
        with open(text_file.content.path) as f:
            lines_amount = get_lines_amount_for(f)
            f.seek(0)

            if start_index > 0:
                for _ in range(start_index):
                    next(f, None)

            for index, line in enumerate(f, start=start_index + 1):
                
                # --- INTELLIGENT CHECK (Co 1 sekundę) ---
                current_time = time.time()
                if current_time - last_check_time > 1.0:
                    update_progress(index, lines_amount, obj)
                    check_interruption(js_id, {
                        'nodes': nodes_tmp,
                        'edges': edges_tmp,
                        'index': index,
                        'info_data': data.get('info')
                    })
                    last_check_time = current_time

                if line.startswith('c') or line.startswith('C') or line in ['', ' ']:
                    continue
                if line.startswith('p'):
                    data['info'] = line.replace("\n", "").split(' ')
                else:
                    numbers = [int(x) for x in list(filter(lambda x: x != '', line.strip().split(' ')))[:-1]]
                    if not numbers:
                        continue
                    for n in numbers:
                        v = abs(n)
                        if v not in nodes_tmp:
                            nodes_tmp[v] = {"id": v, "label": str(v)}

                    # --- LOGIKA KRAWĘDZI (RĘCZNA KONSTRUKCJA) ---
                    # Używamy sorted(), aby krawędź (1,2) i (2,1) była tym samym obiektem
                    pairs_to_process = []
                    
                    if len(numbers) == 2:
                        pairs_to_process.append(tuple(sorted(map(lambda x: abs(x), numbers))))
                    else:
                        for p in itertools.combinations(numbers, 2):
                            pairs_to_process.append(tuple(sorted(map(lambda x: abs(x), p))))

                    for p in pairs_to_process:
                        # p jest krotką (source, target)
                        try:
                            # Próba zwiększenia opacity istniejącej krawędzi
                            edges_tmp[p]["color"]["opacity"] += 0.1
                            # Opcjonalnie: clamp opacity do 1.0
                            if edges_tmp[p]["color"]["opacity"] > 1.0:
                                edges_tmp[p]["color"]["opacity"] = 1.0
                        except KeyError:
                            # Tworzenie nowej krawędzi (BEZ użycia vis_directed.add_edge)
                            edges_tmp[p] = {
                                "from": p[0], 
                                "to": p[1], 
                                "arrows": "to", # Dodajemy strzałkę, bo to "Directed" graph
                                "color": {
                                    "color": '#000000', 
                                    "opacity": 0.1
                                }
                            }

        data['nodes'] = [v for k, v in nodes_tmp.items()]
        data['edges'] = [v for k, v in edges_tmp.items()]

        obj.content = json.dumps(data)
        obj.status = 'done'
        obj.progress = 'Progress: 100.0%'
        obj.save()

    except Exception as e:
        # Ten blok wyłapie błąd i wypisze go w konsoli zamiast cichego crasha
        print(f"CRITICAL ERROR in SAT_VIS_DIRECTED: {e}")
        import traceback
        traceback.print_exc()
        # Opcjonalnie ustaw status na error w bazie, żebyś widział w GUI
        obj.status = 'error'
        obj.save()
        raise e


@app.task()
def create_sat_vis_2clause(obj_id, js_id, js_format, selected_vars, resume_state=None):
    print("SAT_VIS_2-Clauses_Interaction_Graph")
    obj = JsonFile.objects.get(id=js_id)

    if not resume_state:
        obj.status = 'pending'
        obj.save()

    data = {
        "info": None,
        "nodes": [],
        "edges": [],
        "options": vis_2clause.options
    }

    nodes_tmp = {}
    edges_tmp = {}
    start_index = 0

    if resume_state:
        print(f"Resuming 2-clause from line {resume_state.get('index', 0)}")
        nodes_tmp = resume_state.get('nodes', {})
        # Naprawa kluczy (str -> int)
        nodes_tmp = {int(k): v for k, v in nodes_tmp.items()}
        edges_tmp = restore_tuple_keys(resume_state.get('edges', {}))
        start_index = resume_state.get('index', 0)
        data['info'] = resume_state.get('info_data')

    text_file = TextFile.objects.get(id=obj_id)
    
    # ZMIENNA CZASOWA
    last_check_time = time.time()

    with open(text_file.content.path) as f:
        text = File(f)
        lines_amount = get_lines_amount_for(f)
        f.seek(0)

        if start_index > 0:
            for _ in range(start_index):
                next(f, None)

        for index, line in enumerate(f, start=start_index + 1):
            
            # --- ZEWNĘTRZNY CHECK (co 1 sekundę) ---
            current_time = time.time()
            if current_time - last_check_time > 1.0:
                update_progress(index, lines_amount, obj)
                check_interruption(js_id, {
                    'nodes': nodes_tmp,
                    'edges': edges_tmp,
                    'index': index,
                    'info_data': data.get('info')
                })
                last_check_time = current_time

            if line.startswith('c') or line.startswith('C') or line in ['', ' ']:
                continue
            if line.startswith('p'):
                data['info'] = line.replace("\n", "").split(' ')
            else:
                numbers = [int(x) for x in list(filter(lambda x: x != '', line.strip().split(' ')))[:-1]]
                if not numbers:
                    continue
                for n in numbers:
                    v = abs(n)
                    if v not in nodes_tmp:
                        nodes_tmp[v] = {"id": v, "label": str(v)}

                if len(numbers) == 2:
                    id2c = '2c' + str(sorted(numbers))
                    if numbers[0] > 0 and numbers[1] > 0:
                        ids = list(sorted(map(lambda x: abs(x), numbers)))
                        try:
                            vis_2clause.inc_edge(edges_tmp[id2c])
                        except KeyError:
                            edges_tmp[id2c] = vis_2clause.positive_positive(ids[0], ids[1])
                    elif numbers[0] < 0 and numbers[1] < 0:
                        ids = list(sorted(map(lambda x: abs(x), numbers)))
                        try:
                            vis_2clause.inc_edge(edges_tmp[id2c])
                        except KeyError:
                            edges_tmp[id2c] = vis_2clause.negative_negative(ids[0], ids[1])
                    else:
                        ids = list(map(lambda x: abs(x), sorted(numbers)))
                        try:
                            vis_2clause.inc_edge(edges_tmp[id2c])
                        except KeyError:
                            edges_tmp[id2c] = vis_2clause.negative_positive(ids[0], ids[1])
                else:
                    # --- WEWNĘTRZNY CHECK (z dławikiem) ---
                    comb_counter = 0
                    for p in itertools.combinations(numbers, 2):
                        comb_counter += 1
                        if comb_counter % 5000 == 0:
                            current_time_inner = time.time()
                            if current_time_inner - last_check_time > 1.0:
                                check_interruption(js_id, {
                                    'nodes': nodes_tmp,
                                    'edges': edges_tmp,
                                    'index': index,
                                    'info_data': data.get('info')
                                })
                                last_check_time = current_time_inner

                        p = tuple(sorted(map(lambda x: abs(x), p)))
                        try:
                            vis_2clause.inc_edge(edges_tmp[p])
                        except KeyError:
                            edges_tmp[p] = vis_2clause.gt_2clause(p[0], p[1])

    data['nodes'] = [v for k, v in nodes_tmp.items()]
    data['edges'] = [v for k, v in edges_tmp.items()]

    obj.content = json.dumps(data)
    obj.status = 'done'
    obj.progress = 'Progress: 100.0%'
    obj.save()

@app.task()
def create_sat_vis_dpll(obj_id, js_id, js_format, selected_vars, resume_state=None):
    print("SAT_VIS_DPLL_SOLVER_VISUALIZATION")
    obj = JsonFile.objects.get(id=js_id)

    if not resume_state:
        obj.status = 'pending'
        obj.progress = 'DPLL Sat-Solver working...'
        obj.save()

    data = {
        "info": None,
        "moms_nodes": [],
        "moms_edges": [],
        "dlis_nodes": [],
        "dlis_edges": [],
        "jw_nodes": [],
        "jw_edges": [],
        "options": vis_dpll.options
    }

    # --- 1. INICJALIZACJA STANU ---
    # Lista heurystyk, które już zakończyliśmy
    processed_heuristics = []

    if resume_state:
        print(f"Resuming DPLL. Already processed: {resume_state.get('processed_heuristics')}")
        # Przywracamy dotychczas obliczone dane
        saved_data = resume_state.get('data', {})
        data.update(saved_data)
        processed_heuristics = resume_state.get('processed_heuristics', [])

    heuristic_name_map = {1: 'DLIS', 2: 'Jeroslow Wang', 3: 'MOMS'}
    heuristic_output_drop = {1: ["dlis_nodes", "dlis_edges"], 2: ["jw_nodes", "jw_edges"],
                             3: ["moms_nodes", "moms_edges"]}

    text_file = TextFile.objects.get(id=obj_id)

    # Lista heurystyk do wykonania
    heuristics_to_run = [3, 1, 2]

    for heuristic_type in heuristics_to_run:
        
        # --- 2. POMIJANIE ZROBIONYCH ---
        if heuristic_type in processed_heuristics:
            continue

        # --- 3. CHECK INTERRUPTION (Między heurystykami) ---
        # Zapisujemy stan PRZED rozpoczęciem kolejnej ciężkiej operacji
        check_interruption(js_id, {
            'data': data,
            'processed_heuristics': processed_heuristics
        })
        # ---------------------------------------------------

        idpll = DpllIteration(text_file.content.path, heuristic_type)
        obj.progress = 'DPLL Sat-Solver working [' + heuristic_name_map[heuristic_type] + '] ...'
        obj.save()
        
        # Tej operacji nie przerywamy w trakcie (chyba że wejdziesz w kod DpllIteration)
        idpll.run()
        
        obj.progress = 'Building visualization tree [' + heuristic_name_map[heuristic_type] + '] ...'
        obj.save()
        
        dpll_tree = DpllTree(idpll.assignment_trail)
        dpll_tree.build_tree()
        dpll_tree.visualize_tree()

        data[heuristic_output_drop[heuristic_type][0]] = [v for k, v in dpll_tree.v_nodes.items()]
        data[heuristic_output_drop[heuristic_type][1]] = [v for k, v in dpll_tree.v_edges.items()]

        # Oznaczamy jako wykonane
        processed_heuristics.append(heuristic_type)

    obj.content = json.dumps(data)
    obj.status = 'done'
    obj.progress = 'Progress: 100.0%'
    obj.save()


@app.task()
def create_sat_vis_distribution(obj_id, js_id, js_format, selected_vars, resume_state=None):
    print("SAT_VIS_Distribution")
    obj = JsonFile.objects.get(id=js_id)

    if not resume_state:
        obj.status = 'pending'
        obj.save()

    data = {
        "info": None,
        "labels": [],
        "positive": [],
        "negative": []
    }

    # --- 1. INICJALIZACJA STANU ---
    positive = None
    negative = None
    labels = []
    start_index = 0

    if resume_state:
        print(f"Resuming Distribution from line {resume_state.get('index')}")
        start_index = resume_state.get('index', 0)
        data['info'] = resume_state.get('info_data')
        labels = resume_state.get('labels', [])
        
        # Odtwarzanie Numpy Arrays z list
        # JSON zapisał je jako listy, tutaj musimy wrócić do numpy, żeby operacje += działały
        p_list = resume_state.get('positive_list')
        n_list = resume_state.get('negative_list')
        if p_list: positive = np.array(p_list)
        if n_list: negative = np.array(n_list)

    text_file = TextFile.objects.get(id=obj_id)

    with open(text_file.content.path) as f:
        text = File(f)
        lines_amount = get_lines_amount_for(f)
        f.seek(0) # Reset po liczeniu linii

        # --- 2. FAST FORWARD ---
        if start_index > 0:
            for _ in range(start_index):
                next(f, None)

        for index, line in enumerate(f, start=start_index + 1):
            
            # --- 3. CHECK INTERRUPTION ---
            if index % 100 == 0: # Co 100 linii, bo to szybka pętla
                update_progress(index, lines_amount, obj)
                
                # Stan do zapisu. NumpyEncoder w create_json zamieni np.array na listy
                check_interruption(js_id, {
                    'index': index,
                    'info_data': data.get('info'),
                    'labels': labels,
                    'positive_list': positive, # Encoder to obsłuży
                    'negative_list': negative
                })
            # -----------------------------

            if line.startswith('c') or line.startswith('C') or line in ['', ' ']:
                continue
            
            if line.startswith('p'):
                # Jeśli wznawiamy pracę i już mamy 'positive', nie resetujemy go!
                if positive is None:
                    number_of_variables = int((line.split(' '))[2])
                    positive = np.zeros((number_of_variables,), dtype=int)
                    negative = np.zeros((number_of_variables,), dtype=int)
                    labels = []
                    for i in range(number_of_variables - 1):
                        labels.append(str(i + 1))

                data['info'] = line.replace("\n", "").split(' ')
                # data['info'][3].replace("\n", "") # To nic nie robiło w oryginale (string immutable), ale zostawiam
            else:
                # Parsowanie
                numbers = [int(x) for x in list(filter(lambda x: x != '', line.strip().split(' ')))[:-1]]

                # Jeśli plik jest uszkodzony i nie było linii 'p', positive może być None
                if positive is not None:
                    for n in numbers:
                        if n > 0:
                            positive[n - 1] += 1
                        if n < 0:
                            negative[(n * (-1)) - 1] += 1

    # Finalizacja danych
    data['labels'] = labels
    if positive is not None:
        data['positive'] = positive.tolist()
        data['negative'] = negative.tolist()
    else:
        # Fallback jeśli plik był pusty/zły
        data['positive'] = []
        data['negative'] = []

    obj.content = json.dumps(data)
    obj.status = 'done'
    obj.progress = 'Progress: 100.0%'
    obj.save()
    return obj.content

@app.task()
def create_sat_vis_factor(obj_id, js_id, js_format, selected_vars, resume_state=None):
    print("SAT_VIS_FACTOR_GRAPH_VISUALIZATION")
    obj = JsonFile.objects.get(id=js_id)

    if not resume_state:
        obj.status = 'pending'
        obj.save()

    data = {
        "info": None,
        "nodes": [],
        "edges": []
    }

    nodes_tmp = {}
    edges_tmp = {}
    start_index = 0
    # Specyficzne dla Factor Graph liczniki
    factor_cnt = 0 

    if resume_state:
        print(f"Resuming Factor Graph from line {resume_state.get('index')}")
        nodes_tmp = resume_state.get('nodes', {})
        nodes_tmp = {k if isinstance(k, str) and k.startswith('f') else int(k): v for k, v in nodes_tmp.items()}
        edges_tmp = restore_tuple_keys(resume_state.get('edges', {}))
        start_index = resume_state.get('index', 0)
        factor_cnt = resume_state.get('factor_cnt', 0) # Ważne przy wznawianiu!
        data['info'] = resume_state.get('info_data')

    text_file = TextFile.objects.get(id=obj_id)
    
    # --- ZMIENNA CZASOWA ---
    last_check_time = time.time()

    with open(text_file.content.path) as f:
        lines_amount = get_lines_amount_for(f)
        f.seek(0)

        if start_index > 0:
            for _ in range(start_index):
                next(f, None)

        for index, line in enumerate(f, start=start_index + 1):
            
            # --- INTELLIGENT CHECK (Co 1 sekundę) ---
            current_time = time.time()
            if current_time - last_check_time > 1.0:
                update_progress(index, lines_amount, obj)
                check_interruption(js_id, {
                    'nodes': nodes_tmp,
                    'edges': edges_tmp,
                    'index': index,
                    'factor_cnt': factor_cnt, # Musimy zapisać licznik faktorów
                    'info_data': data.get('info')
                })
                last_check_time = current_time
            # ----------------------------------------

            if line.startswith('c') or line.startswith('C') or line in ['', ' ']:
                continue
            if line.startswith('p'):
                data['info'] = line.replace("\n", "").split(' ')
            else:
                numbers = [int(x) for x in list(filter(lambda x: x != '', line.strip().split(' ')))[:-1]]
                if not numbers:
                    continue
                
                # W Factor Graph dodajemy węzeł "Faktora" (kwadracik) dla każdej linii
                factor_cnt += 1
                factor_key = 'f' + str(factor_cnt)
                nodes_tmp[factor_key] = {"id": factor_key, "label": '', "group": 'factor'}

                for n in numbers:
                    v = abs(n)
                    if v not in nodes_tmp:
                        nodes_tmp[v] = {"id": v, "label": str(v), "group": 'variable'}
                    
                    # Krawędź między zmienną a faktorem
                    edge_key = (factor_key, v)
                    # W Factor graph zazwyczaj krawędzie są unikalne per linia, 
                    # więc proste przypisanie wystarczy
                    if n > 0:
                        edges_tmp[edge_key] = {"from": factor_key, "to": v, "color": {"color": 'green'}}
                    else:
                        edges_tmp[edge_key] = {"from": factor_key, "to": v, "color": {"color": 'red', "dashes": True}}

    data['nodes'] = [v for k, v in nodes_tmp.items()]
    data['edges'] = [v for k, v in edges_tmp.items()]

    obj.content = json.dumps(data)
    obj.status = 'done'
    obj.progress = 'Progress: 100.0%'
    obj.save()


@app.task()
def create_sat_vis_interaction(obj_id, js_id, js_format, selected_vars, resume_state=None):
    print("SAT_VIS_INTERACTION STARTED", flush=True) # flush=True wymusza wypisanie logu
    obj = JsonFile.objects.get(id=js_id)

    if not resume_state:
        obj.status = 'pending'
        obj.save()

    data = {
        "info": None,
        "nodes": [],
        "edges": []
    }

    nodes_tmp = {}
    edges_tmp = {}
    start_index = 0

    if resume_state:
        print(f"Resuming SAT_VIS_INTERACTION from line {resume_state.get('index')}", flush=True)
        nodes_tmp = resume_state.get('nodes', {})
        nodes_tmp = {int(k): v for k, v in nodes_tmp.items()} # Fix int keys
        edges_tmp = restore_tuple_keys(resume_state.get('edges', {}))
        start_index = resume_state.get('index', 0)
        data['info'] = resume_state.get('info_data')

    text_file = TextFile.objects.get(id=obj_id)
    
    # ZMIENNA POMOCNICZA DO CZASU
    last_check_time = time.time()

    with open(text_file.content.path) as f:
        text = File(f)
        lines_amount = get_lines_amount_for(f)
        f.seek(0)

        if start_index > 0:
            for _ in range(start_index):
                next(f, None)

        for index, line in enumerate(f, start=start_index):
            
            # 1. ZEWNĘTRZNY CHECK (co linię)
            # Sprawdzamy czas - jeśli minęła sekunda od ostatniego sprawdzenia
            current_time = time.time()
            if current_time - last_check_time > 1.0:
                print(f"Checking interruption at line {index}...", flush=True)
                update_progress(index, lines_amount, obj)
                check_interruption(js_id, {
                    'nodes': nodes_tmp,
                    'edges': edges_tmp,
                    'index': index,
                    'info_data': data.get('info')
                })
                last_check_time = current_time # Reset zegara

            if line.startswith('c') or line.startswith('C') or line in ['', ' ']:
                continue
            if line.startswith('p'):
                data['info'] = line.replace("\n", "").split(' ')
            else:
                numbers = [int(x) for x in list(filter(lambda x: x != '', line.strip().split(' ')))[:-1]]
                if not numbers:
                    continue
                for n in numbers:
                    y = abs(n)
                    if y not in nodes_tmp:
                        nodes_tmp[y] = {"id": y, "label": str(y)}

                # 2. WEWNĘTRZNA PĘTLA - RÓWNIEŻ Z CZASEM
                comb_counter = 0
                for k in itertools.combinations(numbers, 2):
                    comb_counter += 1
                    
                    # Sprawdzamy co 5000 iteracji, ALE TYLKO JEŚLI minęła sekunda
                    # To bardzo tania operacja (modulo), a time() robimy rzadziej
                    if comb_counter % 5000 == 0:
                        current_time_inner = time.time()
                        if current_time_inner - last_check_time > 1.0:
                            print(f"Checking interruption inside line {index} (comb {comb_counter})...", flush=True)
                            check_interruption(js_id, {
                                'nodes': nodes_tmp,
                                'edges': edges_tmp,
                                'index': index, 
                                'info_data': data.get('info')
                            })
                            last_check_time = current_time_inner

                    k = tuple(sorted(map(lambda c: abs(c), k)))
                    try:
                        edges_tmp[k]["color"]["opacity"] += 0.1
                    except KeyError:
                        edges_tmp[k] = {"from": k[0], "to": k[1], "color": {"color": '#000000',
                                                                            "opacity": 0.1}}

    data['nodes'] = [v for k, v in nodes_tmp.items()]
    data['edges'] = [v for k, v in edges_tmp.items()]

    obj.content = json.dumps(data)
    obj.status = 'done'
    obj.progress = 'Progress: 100.0%'
    obj.save()

@app.task()
def create_sat_vis_cluster(obj_id, js_id, js_format, selected_vars, resume_state=None):
    print("SAT_VIS_CLUSTER")
    obj = JsonFile.objects.get(id=js_id)

    if not resume_state:
        obj.status = 'pending'
        obj.save()

    data = {
        'clusteredNetwork': {'edges': [], 'nodes': []},
        'wholeNetwork': {'edges': [], 'nodes': []}
    }

    # --- 1. INICJALIZACJA STANU ---
    edges_tmp = []
    start_index = 0
    parsing_done = False # Flaga, czy skończyliśmy już parsować plik

    if resume_state:
        print(f"Resuming SAT_VIS_CLUSTER from line {resume_state.get('index')}")
        # Przywracamy edges_tmp (konwersja list na tuple dla igraph)
        edges_list = resume_state.get('edges_tmp', [])
        edges_tmp = [tuple(e) for e in edges_list]
        
        start_index = resume_state.get('index', 0)
        parsing_done = resume_state.get('parsing_done', False)
        data['info'] = resume_state.get('info_data')

    text_file = TextFile.objects.get(id=obj_id)
    
    # --- FAZA 1: PARSOWANIE PLIKU ---
    if not parsing_done:
        with open(text_file.content.path) as f:
            text = File(f)
            lines_amount = get_lines_amount_for(f)
            f.seek(0)

            # Fast Forward
            if start_index > 0:
                for _ in range(start_index):
                    next(f, None)

            for index, line in enumerate(f, start=start_index):
                
                # Check Interruption w trakcie parsowania
                if index % 50 == 0:
                    update_progress(index, lines_amount, obj)
                    check_interruption(js_id, {
                        'edges_tmp': edges_tmp,
                        'index': index,
                        'parsing_done': False,
                        'info_data': data.get('info')
                    })

                if line.startswith('c') or line.startswith('C') or line in ['', ' ']:
                    continue
                if line.startswith('p'):
                    data['info'] = line.replace("\n", "").split(' ')
                else:
                    numbers = [int(x) for x in list(filter(lambda x: x != '', line.strip().split(' ')))[:-1]]
                    if not numbers:
                        continue

                    for k in itertools.combinations(numbers, 2):
                        k = tuple(sorted(map(lambda c: abs(c), k)))
                        edges_tmp.append((k[0], k[1]))
        
        # Oznaczamy koniec parsowania
        parsing_done = True
        # Zapisujemy stan po parsowaniu, przed ciężkimi obliczeniami
        check_interruption(js_id, {
            'edges_tmp': edges_tmp,
            'index': 0,
            'parsing_done': True,
            'info_data': data.get('info')
        })

    # --- FAZA 2: OBLICZENIA IGRAPH ---
    # Tego nie da się łatwo przerwać w środku funkcji bibliotecznych,
    # ale dajemy punkty kontrolne między krokami.

    obj.progress = 'Calculating Graph...'
    obj.save()

    if not edges_tmp:
        # Obsługa pustego grafu
        obj.content = json.dumps(data)
        obj.status = 'done'
        obj.save()
        return obj

    g = Graph(edges_tmp)
    g.delete_vertices(0)
    g.simplify()

    # Punkt kontrolny przed heavy calculation
    check_interruption(js_id, {'edges_tmp': edges_tmp, 'parsing_done': True, 'info_data': data.get('info')})

    dendogram = g.community_edge_betweenness()
    clusters = dendogram.as_clustering()
    membership = clusters.membership

    # Punkt kontrolny przed layoutem
    check_interruption(js_id, {'edges_tmp': edges_tmp, 'parsing_done': True, 'info_data': data.get('info')})

    layout1 = g.layout_kamada_kawai()
    # i = g.community_infomap() # To było nieużywane w oryginalnym kodzie, ale zostawiam

    unique_membership_classes = len(set(membership))
    pal = drawing.colors.ClusterColoringPalette(unique_membership_classes)

    clustered = g.copy()
    clustered.contract_vertices(membership, combine_attrs='max')
    clustered.simplify()

    # Generowanie JSON-a wynikowego
    for vertex, cluster in zip(g.vs.indices, membership):
        data['wholeNetwork']['nodes'].append({
            'color': rgb2hex(pal.get(cluster)),
            'id': vertex,
            'label': str(vertex),
            'cluster': cluster
        })

    for edge in g.get_edgelist():
        data['wholeNetwork']['edges'].append({
            'color': {'color': '#888888', 'opacity': 1},
            'from': edge[0],
            'id': f"{edge[0]}_{edge[1]}",
            'to': edge[1],
            'width': 1
        })

    clustered_layout = clustered.layout_kamada_kawai()

    for vertex_idx in clustered.vs.indices:
        data['clusteredNetwork']['nodes'].append({
            'color': rgb2hex(pal.get(vertex_idx)),
            'id': vertex_idx,
            'label': f"Cluster {vertex_idx}",
            'size': 30 + (clustered.degree(vertex_idx) * 3),
            'x': clustered_layout[vertex_idx][0] * 150,
            'y': clustered_layout[vertex_idx][1] * 150
        })

    for edge in clustered.get_edgelist():
        data['clusteredNetwork']['edges'].append({
            'color': {'color': '#888888', 'opacity': 1},
            'from': edge[0],
            'id': str(edge[0]) + '_' + str(edge[1]),
            'to': edge[1]
        })
        
    obj.content = json.dumps(data)
    obj.status = 'done'
    obj.progress = 'Progress: 100.0%'
    obj.save()


@app.task()
def create_sat_vis_matrix(obj_id, js_id, js_format, selected_vars, resume_state=None):
    print("SAT_VIS_MATRIX")
    obj = JsonFile.objects.get(id=js_id)

    if not resume_state:
        obj.status = 'pending'
        obj.save()

    data = {
        "info": None,
        "labels": [],
        "rows": []
    }

    # --- 1. INICJALIZACJA STANU ---
    start_index = 0

    if resume_state:
        print(f"Resuming SAT_VIS_MATRIX from line {resume_state.get('index')}")
        start_index = resume_state.get('index', 0)
        data = resume_state.get('data_snapshot', data)
        # data['rows'] może być duże, więc wczytywanie może chwilę potrwać

    text_file = TextFile.objects.get(id=obj_id)
    with open(text_file.content.path) as f:
        text = File(f)
        lines_amount = get_lines_amount_for(f)
        f.seek(0)

        # Fast Forward
        if start_index > 0:
            for _ in range(start_index):
                next(f, None)

        # W oryginale 'enumerate' domyślne (od 0), więc start=start_index
        for index, line in enumerate(f, start=start_index):
            
            # --- Check Interruption ---
            if index % 50 == 0:
                update_progress(index, lines_amount, obj)
                check_interruption(js_id, {
                    'index': index,
                    'data_snapshot': data # Zapisujemy całą strukturę rows/labels
                })
            # --------------------------

            if line.startswith('c') or line.startswith('C') or line in ['', ' ']:
                continue
            
            if line.startswith('p'):
                # Inicjalizacja macierzy (tylko jeśli rows jest puste, żeby nie nadpisać przy wznowieniu)
                if not data['rows']:
                    data['info'] = line.replace("\n", "").split(' ')
                    numberOfVariables = int(data['info'][-2])
                    for indx1 in range(numberOfVariables):
                        data['labels'].append(str(indx1))
                        tmpRow = {"dependencies": []}
                        for indx2 in range(numberOfVariables):
                            if indx1 != indx2:
                                tmpRow['dependencies'].append({"positive": 0, "negative": 0})
                            else:
                                tmpRow['dependencies'].append({"positive": -1, "negative": -1})
                        data['rows'].append(tmpRow)
            else:
                numbers = [int(x) for x in list(filter(lambda x: x != '', line.strip().split(' ')))[:-1]]
                if not numbers:
                    continue
                
                # Zabezpieczenie: jeśli nie było linii 'p' i rows puste, pomijamy
                if not data['rows']:
                    continue

                for n1 in numbers:
                    for n2 in numbers:
                        if n1 == n2:
                            continue
                        if n1 > 0:
                            data['rows'][abs(n1) - 1]['dependencies'][abs(n2) - 1]['positive'] += 1
                        else:
                            data['rows'][abs(n1) - 1]['dependencies'][abs(n2) - 1]['negative'] += 1

    obj.content = json.dumps(data)
    obj.status = 'done'
    obj.progress = 'Progress: 100.0%'
    obj.save()

@app.task()
def create_sat_vis_tree(obj_id, js_id, js_format, selected_vars, resume_state=None):
    print("SAT_VIS_TREE")

    obj = JsonFile.objects.get(id=js_id)

    if not resume_state:
        obj.status = 'pending'
        obj.save()

    data = {
        "info": None,
        "nodes": [],
        "edges": []
    }

    # --- 1. STATE INITIALIZATION ---
    formulas = []
    start_index = 0
    parsing_done = False

    if resume_state:
        print(f"Resuming SAT_VIS_TREE from line {resume_state.get('index')}")
        formulas = resume_state.get('formulas', [])
        start_index = resume_state.get('index', 0)
        parsing_done = resume_state.get('parsing_done', False)
        data['info'] = resume_state.get('info_data')

    text_file = TextFile.objects.get(id=obj_id)
    
    # --- PHASE 1: PARSING ---
    if not parsing_done:
        with open(text_file.content.path) as f:
            text = File(f)
            lines_amount = get_lines_amount_for(f)
            f.seek(0) # Reset after counting

            # Fast Forward
            if start_index > 0:
                for _ in range(start_index):
                    next(f, None)

            # Note: enumerate uses start=start_index for correct index tracking
            for index, line in enumerate(f, start=start_index):
                
                # Check Interruption
                if index % 50 == 0:
                    update_progress(index, lines_amount, obj)
                    check_interruption(js_id, {
                        'formulas': formulas,
                        'index': index,
                        'parsing_done': False,
                        'info_data': data.get('info')
                    })

                if is_comment(line):
                    continue
                if is_info(line):
                    data['info'] = get_info_array(line)
                else:
                    formulas.append(get_numbers(line))
        
        parsing_done = True
        # Save state after parsing, before tree construction
        check_interruption(js_id, {
            'formulas': formulas,
            'index': 0,
            'parsing_done': True,
            'info_data': data.get('info')
        })

    # --- PHASE 2: TREE CONSTRUCTION ---
    # This part is memory intensive and recursive. 
    # We check interruption right before starting it.
    
    obj.progress = 'Building Formula Tree...'
    obj.save()

    if formulas:
        # Check one last time before the heavy lift
        check_interruption(js_id, {
            'formulas': formulas, 
            'parsing_done': True, 
            'info_data': data.get('info')
        })

        tree = FormulaTree(formulas, 0)
        tree.serialize()
        data['nodes'] = tree.nodes
        data['edges'] = tree.edges

    obj.content = json.dumps(data)
    obj.status = 'done'
    obj.progress = 'Progress: 100.0%'
    obj.save()


@app.task()
def create_sat_vis_resolution(obj_id, js_id, js_format, selected_vars, resume_state=None):
    print("SAT_VIS_RESOLUTION")
    obj = JsonFile.objects.get(id=js_id)

    if not resume_state:
        obj.status = 'pending'
        obj.save()

    data = {
        "info": None,
        "nodes": [],
        "edges": []
    }

    # --- 1. STATE INITIALIZATION ---
    nodes_tmp = {}
    edges_tmp = {}
    variables = {}
    clause = 0
    start_index = 0
    parsing_done = False

    if resume_state:
        print(f"Resuming SAT_VIS_RESOLUTION from line {resume_state.get('index')}")
        nodes_tmp = resume_state.get('nodes_tmp', {})
        # Edges might have tuple keys if we interrupted in phase 2
        edges_tmp = restore_tuple_keys(resume_state.get('edges_tmp', {}))
        
        # Restore variables map. Keys are integers (literals), JSON makes them strings.
        # We need to convert keys back to int.
        raw_vars = resume_state.get('variables', {})
        variables = {int(k): v for k, v in raw_vars.items()}
        
        clause = resume_state.get('clause', 0)
        start_index = resume_state.get('index', 0)
        parsing_done = resume_state.get('parsing_done', False)
        data['info'] = resume_state.get('info_data')

    text_file = TextFile.objects.get(id=obj_id)
    
    # --- PHASE 1: PARSING ---
    if not parsing_done:
        with open(text_file.content.path) as f:
            text = File(f)
            lines_amount = get_lines_amount_for(f)
            f.seek(0)
            print("Working on vis resolution.")

            # Fast Forward
            if start_index > 0:
                for _ in range(start_index):
                    next(f, None)

            for index, line in enumerate(f, start=start_index + 1):

                # Check Interruption
                if index % 50 == 0:
                    update_progress(index, lines_amount, obj)
                    check_interruption(js_id, {
                        'nodes_tmp': nodes_tmp,
                        'variables': variables, # Dictionary {int: list}
                        'clause': clause,
                        'index': index,
                        'parsing_done': False,
                        'info_data': data.get('info')
                    })

                if line.startswith('c') or line.startswith('C') or line in ['', ' ']:
                    continue
                if line.startswith('p'):
                    data['info'] = line.replace("\n", "").split(' ')
                else:
                    numbers = [int(x) for x in list(filter(lambda x: x != '', line.strip().split(' ')))[:-1]]
                    if not numbers:
                        continue
                    clause += 1
                    nodes_tmp[clause] = {"id": clause, "label": 'C_' + str(clause)}
                    for n in numbers:
                        if n not in variables and (selected_vars is None or len(selected_vars) == 0 or
                                                n in selected_vars or -n in selected_vars):
                            variables[n] = []
                        if n in variables:
                            variables[n].append(clause)
        
        parsing_done = True
        # Checkpoint after parsing
        check_interruption(js_id, {
            'nodes_tmp': nodes_tmp,
            'variables': variables,
            'clause': clause,
            'index': 0,
            'parsing_done': True,
            'info_data': data.get('info')
        })

    # --- PHASE 2: EDGE GENERATION ---
    obj.progress = 'Generating Resolution Edges...'
    obj.save()

    # Note: We restart this loop from the beginning if paused here, 
    # because saving iterator state over a dict is unreliable.
    
    # Optimization: Check interruption periodically during the loop
    count = 0
    total_vars = len(variables)
    
    for v, clause_list_1 in variables.items():
        count += 1
        # Check interruption every 100 variables processed
        if count % 100 == 0:
             # We use edges_tmp to save progress so far
             check_interruption(js_id, {
                'nodes_tmp': nodes_tmp,
                'variables': variables,
                'edges_tmp': edges_tmp, # Save edges generated so far
                'clause': clause,
                'parsing_done': True, # We are done parsing
                'info_data': data.get('info')
            })
             
        if v < 0:
            continue
        if -v in variables.keys():
            clause_list_2 = variables[-v]

            for c1 in clause_list_1:
                for c2 in clause_list_2:
                    edges_tmp[(c1, c2)] = {"from": c1, "to": c2}

    data['nodes'] = [v for k, v in nodes_tmp.items()]
    data['edges'] = [v for k, v in edges_tmp.items()]

    obj.content = json.dumps(data)
    obj.status = 'done'
    obj.progress = 'Progress: 100.0%'
    obj.save()

@app.task()
def create_sat_vis_cdcl(obj_id, js_id, js_format, selected_vars, resume_state=None):
    print("SAT_VIS_CDCL_SOLVER_VISUALIZATION")
    obj = JsonFile.objects.get(id=js_id)
    if not resume_state:
        obj.status = 'pending'
        obj.save()
    data = {"info": None, 
            "vsids_nodes": [],
            "vsids_edges": [],
            "dlis_nodes": [],
            "dlis_edges": [],
            "plus_nodes": [],
            "plus_edges": [],
            "options":i_cdcl.options}
    
    processed_heuristics = []
    if resume_state:
        print(f"Resuming CDCL. Already processed: {resume_state.get('processed_heuristics')}")

        saved_data = resume_state.get('data', {})
        data.update(saved_data)
        processed_heuristics = resume_state.get('processed_heuristics', [])
    heuristic_name_map = {1: 'VSIDS',2: 'DLIS'}
    heuristic_output_drop = {1: ["vsids_nodes", "vsids_edges"], 2: ["dlis_nodes", "dlis_edges"]}
    text_file = TextFile.objects.get(id=obj_id)
    heuristics_to_run = [1,2]

    for heuristic_type in heuristics_to_run:
        if heuristic_type in processed_heuristics:
            continue
        check_interruption(js_id, {
            'data': data,
            'processed_heuristics': processed_heuristics
        })
        obj.progress = f'Procesing the file: {heuristic_name_map[heuristic_type]}'
        obj.save()

        filename = text_file.content.path
        dimacs_cnf = open(filename).read()
        formula, num_vars, num_clauses = parse_dimacs_cnf_cdcl(dimacs_cnf)
        
        obj.progress = 'CDCL Sat-Solver working [' + heuristic_name_map[heuristic_type] + '] ...'
        obj.save()
        semantic = False
        if heuristic_type == 1:
            semantic = True
        cdcl_solver = CDCLSolver(formula, heuristic_type, semantic_profile=semantic)
        result, nodes, edges = cdcl_solver.cdcl_solve(formula)
        
        obj.progress = 'Building visualization tree'
        nodes_json, edges_json = made_tree(nodes, edges)

        data[heuristic_output_drop[heuristic_type][0]] = [v for _, v in nodes_json.items()]
        data[heuristic_output_drop[heuristic_type][1]] = [v for _, v in edges_json.items()]
        print(data[heuristic_output_drop[heuristic_type][0]])
        print(data[heuristic_output_drop[heuristic_type][1]])

        if semantic:
            semantic_score = cdcl_solver.profiler.get_semantic_scores()
            inter_nodes, inter_edges = create_inter_plus(formula, semantic_score)
            data["plus_nodes"] = [v for _, v in inter_nodes.items()]
            data["plus_edges"] =  [v for _, v in inter_edges.items()]
        processed_heuristics.append(heuristic_type)
    obj.content = json.dumps(data)
    obj.status = 'done'
    obj.progress = 'Progress: 100.0%'
    obj.save()
@app.task
def create_inter_plus(formula: Formula, semantic_scores: dict):
    # nodes_json[n.id] = {"id": n.id, "label": label, 
    #                         "level": n.decision_level, "color": {"background": n.color},
    #                         "shape": shapes[n.type]}
    # edges_json[e.id] = {"from": e.source, "to":e.target, "color": e.color}
    nodes = {}
    edges = {}
    for v in formula.variables():
        nodes[v] = {"id": v, "label": f'x{v}', "color": {"background": get_semantic_color(semantic_scores[v])}}
    for clause in formula.clauses:
        vars = [l.variable for l in clause.literals]
        for v1 in vars:
            for v2 in vars:
                if v1 < v2:
                    k = tuple((v1, v2))
                    if k not in edges.keys():
                        edges.update({k: {"from": v1, "to": v2, "color": {"color": '#000000',
                                                                            "opacity": 0.1}}})
    return nodes, edges
def get_semantic_color(score):
    start_color = (220, 220, 220)
    end_color = (255, 0, 0)
    r = int(start_color[0] + (end_color[0] - start_color[0]) * score)
    g = int(start_color[1] + (end_color[1] - start_color[1]) * score)
    b = int(start_color[2] + (end_color[2] - start_color[2]) * score)
    
    return "rgb({}, {}, {})".format(r, g, b)
@app.task
def parse_dimacs_cnf_cdcl(content: str) -> Tuple[Formula, int, int]:
    clauses = [Clause([])]
    for line in content.splitlines():
        tokens = line.split()
        if len(tokens) != 0 and tokens[0] not in ("p", "c"):
            for tok in tokens:
                lit = int(tok)
                if lit == 0:
                    clauses.append(Clause([]))
                else:
                    var = abs(lit)
                    neg = lit < 0
                    clauses[-1].literals.append(Literal(var, neg))
        elif len(tokens) != 0 and tokens[0] == "p":
            num_vars = int(tokens[2])
            num_clauses = int(tokens[3])

    if len(clauses[-1]) == 0:
        clauses.pop()

    return (Formula(clauses), num_vars, num_clauses)
from pysat.formula import CNF
@app.task()
def create_sat_vis_what_if(obj_id, js_id, js_format, selected_vars, resume_state=None):
    print("SAT_VIS_WHAT_IF_VISUALIZATION")
    obj = JsonFile.objects.get(id=js_id)
    text_file = TextFile.objects.get(id=obj_id)
    cnf_path = text_file.content.path
    variables = set()
    with open(cnf_path) as f:
        text = File(f)
        for index, line in enumerate(f):
            if line.startswith('c') or line.startswith('C') or line in ['', ' ']:
                continue
            elif line.startswith('p'):
                continue
            else:
                numbers = [int(np.abs(int(x))) for x in list(filter(lambda x: x != '', line.strip().split(' ')))[:-1]]
                numbers = set(numbers)
                variables = variables.union(numbers)
    formula = CNF(from_file=cnf_path)
    solver = Glucose3()
    solver.append_formula(formula.clauses)

    data = {"info": None, 
            "variables": list(variables),
            "edges": {},
            "nodes": {}}
    for var in variables:
        for v in [-var, var]:
            is_ok, implied = solver.propagate(assumptions=[v])
            implied_set = set(implied)
            nodes = []
            edges = []
            for i in range(1, formula.nv + 1):
                state = "neutral"
                color = "#ECF0F1"
                if i == abs(v): 
                    state = "decision"
                    color = "#8400C6"
                elif i in implied_set: 
                    state = "forced_true"
                    color = "#3498DB"
                elif -i in implied_set: 
                    state = "forced_false"
                    color = "#F1C40F"
                if -i in implied_set and i in implied_set:
                    state = "conflict"
                    color = "#F10F0F"
                nodes.append({
                    "id": f"v{i}",
                    "label": f"X{i}",
                    "group": "variable",
                    "color": color,
                    "val": 1 if (i == v or i in implied_set) else (0 if (-i in implied_set or i == -v) else None)
                })
            for idx, clause in enumerate(formula.clauses):
                c_id = f"c{idx}"
                is_sat = any(lit in implied_set or lit == v for lit in clause)
                
                nodes.append({
                    "id": c_id,
                    "label": f"C{idx}",
                    "group": "clause",
                    "shape": "square",
                    "color": "#2ECC71" if is_sat else "#BDC3C7"
                })

                for lit in clause:
                    edges.append({
                        "from": f"v{abs(lit)}",
                        "to": c_id,
                        "color": "#27AE60" if (lit in implied_set or lit == v) else "#7F8C8D"
                    })

            # variants_data["pos" if v > 0 else "neg"] = {"nodes": nodes, "edges": edges}
            st = "pos" if v > 0 else "neg"
            if str(abs(var)) in data['nodes'].keys():
                data['nodes'][str(abs(var))][st] = nodes
            else:
                data['nodes'].update({str(abs(var)): {st: nodes}})
            if str(abs(var)) in data['edges'].keys():
                data['edges'][str(abs(var))][st] = edges
            else:
                data['edges'].update({str(abs(var)): {st: edges}})
            # data['edges'][var][st] = edges
    print(variables)
    obj.content = json.dumps(data)
    obj.status = 'done'
    obj.progress = 'Progress: 100.0%'
    obj.save()
    return obj

@app.task()
def create_sat_landscape(obj_id, js_id, js_format, selected_vars, resume_state=None):
    print("SAT_VIS_LANDSCAPE")
    import umap
    data = {
        "info": None,
        "points": [],
        "solver_path": []
    }
    obj = JsonFile.objects.get(id=js_id)
    text_file = TextFile.objects.get(id=obj_id)
    variables = set()
    clauses = []
    with open(text_file.content.path) as f:
        for index, line in enumerate(f):
            if line.startswith('c') or line.startswith('C') or line in ['', ' ']:
                continue
            elif line.startswith('p'):
                continue
            else:
                raw_clause = [int(x) for x in line.strip().split(' ') if x and x != '0']
                clauses.append(raw_clause)
                variables.update([abs(x) for x in raw_clause])
    variables = sorted(list(variables))
    num_vars = len(variables)

    solver_steps = []
    with Glucose3() as solver:
        formula = CNF(from_file=text_file.content.path)
        solver.append_formula(formula.clauses)
        current_assumptions = []
        
        for v in variables:
            value = random.randint(0, 1)
            neg = 1
            if value:
                neg = -1
            current_assumptions.append(neg * v)
            is_consistent, conflict = solver.propagate(assumptions=current_assumptions)
            
            if is_consistent:
                # Tworzymy pełne przypisanie na podstawie modelu cząstkowego
                # solver.get_model() zwraca to, co już wiemy
                model = solver.get_model() or current_assumptions
                # Tworzymy słownik (uzupełniamy brakujące zmienne zerami)
                step_assignment = {abs(v): 0 for v in variables}
                for lit in model:
                    step_assignment[abs(lit)] = 1 if lit > 0 else 0
                
                solver_steps.append(step_assignment)
            else:
                current_assumptions.pop()
                current_assumptions.append((-1) * neg *v)
    if num_vars <= 11:
        combinations = itertools.product([0, 1], repeat=num_vars)

        samples = [{variables[i]: bit for i, bit in enumerate(combination)} for combination in combinations]
    else:
        samples = []
        local_samples = []
        for step in solver_steps:
            for _ in range(random.randint(1,num_vars)):
                mutated = step.copy()
                for _ in range(random.randint(1, num_vars)):
                    v = random.choice(variables)
                    mutated[v] = 1 - mutated[v]
                local_samples.append(mutated)
        pure_random = []
        for _ in range(1000):
            pure_random.append({v: random.randint(0, 1) for v in variables})
        samples = local_samples + pure_random
    #print(samples)
    costs = []
    num_clauses = len(clauses)
    all_samples = samples + solver_steps
    for s in all_samples:
        costs.append(get_cost(s, clauses, num_clauses))
    #print(costs)
    X = [[v for k, v in s.items()] for s in all_samples]
    reducer = PCA(n_components=2) #umap.UMAP(n_neighbors=15, min_dist=0.1, metric='hamming')
    X_scaled = StandardScaler().fit_transform(X)
    embedding = reducer.fit_transform(X_scaled)
    points = []
    for i in range(len(costs)):
        points.append({'x': float(embedding[i][0]), 'y': float(embedding[i][1]), 'cost': float(costs[i])})
    path = []
    for i in range(len(samples), len(samples)+len(solver_steps)):
        path.append({'x': float(embedding[i][0]), 'y': float(embedding[i][1]), 'cost': float(costs[i])})
    print(path)
    data['points'] = points
    data['path'] = path
    #print(points)


    obj.content = json.dumps(data)
    obj.status = 'done'
    obj.progress = 'Progress: 100.0%'
    obj.save()
    return obj


@app.task
def get_cost(assigment, clauses, num_clauses):
    unsatisfied_count = 0
    for clause in clauses:
        satisfied = False
        for literal in clause:
            var = abs(literal)
            val = assigment[var]
            if (literal > 0 and val == 1) or (literal < 0 and val == 0):
                satisfied = True
                break
        if not satisfied:
            unsatisfied_count += 1

    return unsatisfied_count / num_clauses

@app.task()
def create_variables_list(obj_id, js_id, js_format, selected_vars, resume_state=None):
    print("SAT_VARIABLES")
    obj = JsonFile.objects.get(id=js_id)

    if not resume_state:
        obj.status = 'pending'
        obj.save()

    data = {
        "info": None,
        "variables": []
    }

    # --- 1. INICJALIZACJA STANU ---
    variables = {}
    start_index = 0

    if resume_state:
        print(f"Resuming VARIABLES list from line {resume_state.get('index')}")
        start_index = resume_state.get('index', 0)
        data['info'] = resume_state.get('info_data')
        
        # Odtwarzanie zmiennych: JSON zamienił klucze-inty na stringi.
        # Musimy to naprawić, konwertując klucze z powrotem na int.
        raw_vars = resume_state.get('variables', {})
        variables = {}
        for k, v in raw_vars.items():
            try:
                variables[int(k)] = v
            except ValueError:
                pass # Ignorujemy jeśli klucz nie jest liczbą (choć nie powinno się zdarzyć)

    text_file = TextFile.objects.get(id=obj_id)
    with open(text_file.content.path) as f:
        text = File(f)
        lines_amount = get_lines_amount_for(f)
        f.seek(0) # Reset po liczeniu linii

        # --- 2. FAST FORWARD ---
        if start_index > 0:
            for _ in range(start_index):
                next(f, None)

        for index, line in enumerate(f, start=start_index):

            # --- 3. CHECK INTERRUPTION ---
            if index % 100 == 0:
                update_progress(index, lines_amount, obj)
                check_interruption(js_id, {
                    'variables': variables, # Zostanie zapisane jako {"1": [], "2": []}
                    'index': index,
                    'info_data': data.get('info')
                })
            # -----------------------------

            if line.startswith('c') or line.startswith('C') or line in ['', ' ']:
                continue
            if line.startswith('p'):
                data['info'] = line.replace("\n", "").split(' ')
            else:
                numbers = [int(x) for x in list(filter(lambda x: x != '', line.strip().split(' ')))[:-1]]
                if not numbers:
                    continue
                for n in numbers:
                    # variables.keys() w Python 3 zwraca view, ale 'in' działa szybko
                    if n >= 0 and n not in variables:
                        variables[n] = []
                    if n < 0 and -n not in variables:
                        variables[-n] = []

    data['variables'] = list(variables.keys())

    obj.content = json.dumps(data)
    obj.status = 'done'
    obj.progress = 'Progress: 100.0%'
    obj.save()


@app.task()
def create_raw(obj_id, js_id, js_format, selected_vars, resume_state=None):
    # Dodaliśmy resume_state tylko dla kompatybilności z create_json.
    # Ta funkcja jest "atomowa" (czyta całość naraz), więc nie ma tu pętli do pauzowania.
    
    print("RAW")
    obj = JsonFile.objects.get(id=js_id)
    
    # Mały check na start - jeśli user zapauzował zanim funkcja ruszyła
    check_interruption(js_id, {}) 
    
    text_file = TextFile.objects.get(id=obj_id)
    obj.status = 'pending'
    obj.save()
    
    data = {"raw": ""}
    
    # Tutaj czytamy cały plik naraz. Jeśli jest ogromny, to chwilę potrwa,
    # ale nie da się tego przerwać w połowie bez przepisywania na czytanie chunkami.
    with open(text_file.content.path) as f:
        text = File(f)
        t = text.read()
        data["raw"] = t
        obj.content = json.dumps(data)
        
    obj.status = 'done'
    obj.progress = 'Progress: 100.0%'
    obj.save()


@app.task()
def create_minimized(obj_id, profile_id, resume_state=None):
    # Dodano argument resume_state dla spójności, choć tutaj ciężko o 'wznawianie' procesu binarnego.
    print("MINIMIZING: {}".format(obj_id))
    
    # Sprawdzamy pauzę tylko na starcie.
    # Uwaga: Ten task operuje na TextFile, więc check_interruption musi dostać odpowiednie ID.
    # Zakładam, że task_id to obj_id w kontekście tego wywołania, jeśli nie - trzeba dostosować.
    # W tym przypadku przekażemy pusty słownik, bo nie ma co ratować przed startem.
    check_interruption(obj_id, {}) 

    time.sleep(5)

    base_file = TextFile.objects.get(id=obj_id)
    profile = Profile.objects.get(id=profile_id)

    base_path = base_file.content.path

    satelite_path = re.sub(r'.cnf', '_min.cnf', base_path)
    name = re.sub(r'.cnf', '_min.cnf', base_file.name)

    open(satelite_path, 'w+')
    
    # Tego procesu (Popen) nie da się bezpiecznie zapauzować w połowie.
    # Musi lecieć do końca.
    p = Popen(
        [SATELITE_PATH, base_path, satelite_path],
        stdin=PIPE, stdout=PIPE, stderr=PIPE
    )
    output, err = p.communicate()
    print('OUTPUt {}'.format(output))
    print('ERROR {}'.format(err))
    
    print('basse {}'.format(os.path.isfile(base_path)))
    print('satelite {}'.format(os.path.isfile(satelite_path)))

    with open(satelite_path, 'r') as f:
        text = File(f)

        TextFile.objects.create(
            profile=profile,
            name=name,
            content=text,
            minimized=True
        )

    os.remove(satelite_path)
    print("DONE: {}".format(obj_id))


@app.task()
def create_maxsat_vis_factor(obj_id, js_id, js_format, selected_vars, resume_state=None):
    print("MAXSAT_VIS_FACTOR")
    obj = JsonFile.objects.get(id=js_id)

    if not resume_state:
        obj.status = 'pending'
        obj.save()

    data = {
        "info": None,
        "nodes": [],
        "edges": []
    }

    nodes_tmp = {}
    edges_tmp = {}
    clause_weights = {}
    clause = 0
    start_index = 0

    if resume_state:
        print(f"Resuming MAXSAT_VIS_FACTOR from line {resume_state.get('index')}")
        start_index = resume_state.get('index', 0)
        data['info'] = resume_state.get('info_data')
        
        # Przywracanie kluczy
        raw_nodes = resume_state.get('nodes', {})
        for k, v in raw_nodes.items(): nodes_tmp[int(k)] = v
            
        edges_tmp = restore_tuple_keys(resume_state.get('edges', {}))
        
        raw_weights = resume_state.get('clause_weights', {})
        for k, v in raw_weights.items(): clause_weights[int(k)] = v
            
        clause = resume_state.get('clause', 0)

    text_file = TextFile.objects.get(id=obj_id)
    
    # --- Dławik czasowy ---
    last_check_time = time.time()

    with open(text_file.content.path) as f:
        text = File(f)
        lines_amount = get_lines_amount_for(f)
        f.seek(0)

        if start_index > 0:
            for _ in range(start_index):
                next(f, None)

        for index, line in enumerate(f, start=start_index):
            
            # --- TIME CHECK ---
            current_time = time.time()
            if current_time - last_check_time > 1.0:
                update_progress(index, lines_amount, obj)
                check_interruption(js_id, {
                    'nodes': nodes_tmp,
                    'edges': edges_tmp,
                    'clause_weights': clause_weights,
                    'clause': clause,
                    'index': index,
                    'info_data': data.get('info')
                })
                last_check_time = current_time

            if line.startswith('c') or line.startswith('C') or line in ['', ' ']:
                continue
            if line.startswith('p'):
                data['info'] = line.replace("\n", "").split(' ')
            else:
                numbers = [int(x) for x in list(filter(lambda x: x != '', line.strip().split(' ')))[:-1]]
                if not numbers:
                    continue
                clause += 1
                
                clause_weights[clause] = numbers[0]
                del numbers[0]

                for n in numbers:
                    y = abs(n)
                    if y not in nodes_tmp:
                        nodes_tmp[y] = {"id": y, "label": str(y)}

                for n in numbers:
                    k = (abs(n), -clause)
                    color = 'red' if n < 0 else 'green'
                    edges_tmp[k] = {"from": k[0], "to": k[1], "color": {"color": color, "opacity": 1}}

    # Finalizacja
    if clause_weights:
        min_cw = min(clause_weights.values())
        max_cw = max(clause_weights.values())
        data['nodes'] = [v for k, v in nodes_tmp.items()]
        data['nodes'].extend([get_node(-c, cw, min_cw, max_cw) for c, cw in clause_weights.items()])
        data['edges'] = [v for k, v in edges_tmp.items()]
    else:
        data['nodes'] = []
        data['edges'] = []

    obj.content = json.dumps(data)
    obj.status = 'done'
    obj.progress = 'Progress: 100.0%'
    obj.save()

@app.task()
def create_maxsat_vis_interaction(obj_id, js_id, js_format, selected_vars, resume_state=None):
    print("MAXSAT_VIS_INTERACTION", flush=True)
    obj = JsonFile.objects.get(id=js_id)

    if not resume_state:
        obj.status = 'pending'
        obj.save()

    data = {
        "info": None,
        "nodes": [],
        "edges": []
    }

    # --- 1. INICJALIZACJA STANU ---
    nodes_tmp = {}
    edges_tmp = {}
    start_index = 0

    if resume_state:
        print(f"Resuming MAXSAT_VIS_INTERACTION from line {resume_state.get('index')}")
        nodes_tmp = resume_state.get('nodes', {})
        # Naprawa kluczy-krotek i intów
        edges_tmp = restore_tuple_keys(resume_state.get('edges', {}))
        nodes_tmp = {int(k): v for k, v in nodes_tmp.items()}
        
        start_index = resume_state.get('index', 0)
        data['info'] = resume_state.get('info_data')

    text_file = TextFile.objects.get(id=obj_id)
    
    # --- ZMIENNA CZASOWA (Dławik) ---
    last_check_time = time.time()

    with open(text_file.content.path) as f:
        text = File(f)
        lines_amount = get_lines_amount_for(f)
        f.seek(0)

        # --- 2. FAST FORWARD ---
        if start_index > 0:
            for _ in range(start_index):
                next(f, None)

        for index, line in enumerate(f, start=start_index):
            
            # --- 3. CHECK INTERRUPTION (OUTER - TIME BASED) ---
            # Sprawdzamy czas. Jeśli minęła sekunda, aktualizujemy status.
            current_time = time.time()
            if current_time - last_check_time > 1.0:
                update_progress(index, lines_amount, obj)
                check_interruption(js_id, {
                    'nodes': nodes_tmp,
                    'edges': edges_tmp,
                    'index': index,
                    'info_data': data.get('info')
                })
                last_check_time = current_time
            # -----------------------------

            if line.startswith('c') or line.startswith('C') or line in ['', ' ']:
                continue
            if line.startswith('p'):
                data['info'] = line.replace("\n", "").split(' ')
            else:
                numbers = [int(x) for x in list(filter(lambda x: x != '', line.strip().split(' ')))[:-1]]
                if not numbers:
                    continue
                
                for n in numbers:
                    y = abs(n)
                    if y not in nodes_tmp:
                        nodes_tmp[y] = {"id": y, "label": str(y)}

                # --- 4. INNER LOOP CHECK (Dla bardzo długich klauzul) ---
                comb_counter = 0
                for k in itertools.combinations(numbers, 2):
                    comb_counter += 1
                    
                    # Sprawdzamy co 5000 par, ale tylko jeśli minęła sekunda
                    if comb_counter % 5000 == 0:
                        if time.time() - last_check_time > 1.0:
                            check_interruption(js_id, {
                                'nodes': nodes_tmp,
                                'edges': edges_tmp,
                                'index': index, # Zapisujemy index bieżącej linii
                                'info_data': data.get('info')
                            })
                            last_check_time = time.time()

                    k = tuple(sorted(map(lambda c: abs(c), k)))
                    try:
                        edges_tmp[k]["color"]["opacity"] += 0.1
                    except KeyError:
                        edges_tmp[k] = {"from": k[0], "to": k[1], "color": {"color": '#000000',
                                                                            "opacity": 0.1}}

    data['nodes'] = [v for k, v in nodes_tmp.items()]
    data['edges'] = [v for k, v in edges_tmp.items()]

    obj.content = json.dumps(data)
    obj.status = 'done'
    obj.progress = 'Progress: 100.0%'
    obj.save()


@app.task()
def create_maxsat_vis_cluster(obj_id, js_id, js_format, selected_vars, resume_state=None):
    print("MAXSAT_VIS_CLUSTER")
    obj = JsonFile.objects.get(id=js_id)

    if not resume_state:
        obj.status = 'pending'
        obj.save()

    data = {
        'clusteredNetwork': {'edges': [], 'nodes': []},
        'wholeNetwork': {'edges': [], 'nodes': []}
    }

    edges_tmp = []
    start_index = 0
    parsing_done = False

    if resume_state:
        print(f"Resuming MAXSAT_VIS_CLUSTER from line {resume_state.get('index')}")
        raw_edges = resume_state.get('edges_tmp', [])
        edges_tmp = [tuple(e) for e in raw_edges]
        
        start_index = resume_state.get('index', 0)
        parsing_done = resume_state.get('parsing_done', False)
        data['info'] = resume_state.get('info_data')

    text_file = TextFile.objects.get(id=obj_id)
    
    # --- Dławik czasowy ---
    last_check_time = time.time()
    
    # --- FAZA 1: PARSOWANIE ---
    if not parsing_done:
        with open(text_file.content.path) as f:
            text = File(f)
            lines_amount = get_lines_amount_for(f)
            f.seek(0)

            if start_index > 0:
                for _ in range(start_index):
                    next(f, None)

            for index, line in enumerate(f, start=start_index):
                
                # --- TIME CHECK (OUTER) ---
                current_time = time.time()
                if current_time - last_check_time > 1.0:
                    update_progress(index, lines_amount, obj)
                    check_interruption(js_id, {
                        'edges_tmp': edges_tmp,
                        'index': index,
                        'parsing_done': False,
                        'info_data': data.get('info')
                    })
                    last_check_time = current_time

                if line.startswith('c') or line.startswith('C') or line in ['', ' ']:
                    continue
                if line.startswith('p'):
                    data['info'] = line.replace("\n", "").split(' ')
                else:
                    numbers = [int(x) for x in list(filter(lambda x: x != '', line.strip().split(' ')))[:-1]]
                    if not numbers:
                        continue

                    # --- INNER LOOP PROTECTION (Combinations) ---
                    comb_counter = 0
                    for k in itertools.combinations(numbers, 2):
                        comb_counter += 1
                        if comb_counter % 5000 == 0:
                            if time.time() - last_check_time > 1.0:
                                check_interruption(js_id, {
                                    'edges_tmp': edges_tmp,
                                    'index': index,
                                    'parsing_done': False,
                                    'info_data': data.get('info')
                                })
                                last_check_time = time.time()

                        k = tuple(sorted(map(lambda c: abs(c), k)))
                        edges_tmp.append((k[0], k[1]))
        
        parsing_done = True
        check_interruption(js_id, {
            'edges_tmp': edges_tmp,
            'index': 0,
            'parsing_done': True,
            'info_data': data.get('info')
        })

    # --- FAZA 2: OBLICZENIA IGRAPH ---
    obj.progress = 'Calculating Graph Clusters...'
    obj.save()

    if not edges_tmp:
        obj.content = json.dumps(data)
        obj.status = 'done'
        obj.save()
        return obj

    g = Graph(edges_tmp)
    g.delete_vertices(0)
    g.simplify()

    # Checkpoint przed algorytmem
    if time.time() - last_check_time > 1.0:
        check_interruption(js_id, {'edges_tmp': edges_tmp, 'parsing_done': True, 'info_data': data.get('info')})
        last_check_time = time.time()

    dendogram = g.community_edge_betweenness()
    clusters = dendogram.as_clustering()
    membership = clusters.membership

    # Checkpoint po algorytmie
    if time.time() - last_check_time > 1.0:
        check_interruption(js_id, {'edges_tmp': edges_tmp, 'parsing_done': True, 'info_data': data.get('info')})

    layout1 = g.layout_kamada_kawai()
    i = g.community_infomap()
    pal = drawing.colors.ClusterColoringPalette(len(i))

    clustered = g.copy()
    clustered.contract_vertices(membership, combine_attrs='max')
    clustered.simplify()

    for vertex, cluster in zip(g.vs.indices, membership):
        data['wholeNetwork']['nodes'].append({
            'color': rgb2hex(pal.get(cluster)),
            'id': vertex,
            'label': str(vertex),
            'cluster': cluster
        })

    for edge in g.get_edgelist():
        data['wholeNetwork']['edges'].append({
            'color': {'color': '#888888', 'opacity': 1},
            'from': edge[0],
            'id': str(edge[0]) + '_' + str(edge[1]),
            'to': edge[1]
        })

    clustered_layout = clustered.layout_kamada_kawai()

    for vertex in clustered.vs.indices:
        data['clusteredNetwork']['nodes'].append({
            'color': rgb2hex(pal.get(vertex)),
            'id': vertex,
            'label': str(vertex)
        })

    for edge in clustered.get_edgelist():
        data['clusteredNetwork']['edges'].append({
            'color': {'color': '#888888', 'opacity': 1},
            'from': edge[0],
            'id': str(edge[0]) + '_' + str(edge[1]),
            'to': edge[1]
        })
        
    obj.content = json.dumps(data)
    obj.status = 'done'
    obj.progress = 'Progress: 100.0%'
    obj.save()

@app.task()
def create_maxsat_vis_matrix(obj_id, js_id, js_format, selected_vars, resume_state=None):
    print("MAXSAT_VIS_MATRIX")
    obj = JsonFile.objects.get(id=js_id)

    if not resume_state:
        obj.status = 'pending'
        obj.save()

    data = {
        "info": None,
        "labels": [],
        "rows": []
    }

    start_index = 0

    if resume_state:
        print(f"Resuming MAXSAT_VIS_MATRIX from line {resume_state.get('index')}")
        start_index = resume_state.get('index', 0)
        data = resume_state.get('data_snapshot', data)

    text_file = TextFile.objects.get(id=obj_id)
    
    # --- Dławik czasowy ---
    last_check_time = time.time()

    with open(text_file.content.path) as f:
        text = File(f)
        lines_amount = get_lines_amount_for(f)
        f.seek(0)

        if start_index > 0:
            for _ in range(start_index):
                next(f, None)

        for index, line in enumerate(f, start=start_index):
            
            # --- TIME CHECK (OUTER) ---
            current_time = time.time()
            if current_time - last_check_time > 1.0:
                update_progress(index, lines_amount, obj)
                check_interruption(js_id, {
                    'index': index,
                    'data_snapshot': data
                })
                last_check_time = current_time

            if line.startswith('c') or line.startswith('C') or line in ['', ' ']:
                continue
            
            if line.startswith('p'):
                if not data['rows']:
                    data['info'] = line.replace("\n", "").split(' ')
                    numberOfVariables = int(data['info'][-2])
                    for indx1 in range(numberOfVariables):
                        data['labels'].append(str(indx1))
                        tmpRow = {"dependencies": []}
                        for indx2 in range(numberOfVariables):
                            if indx1 != indx2:
                                tmpRow['dependencies'].append({"positive": 0, "negative": 0})
                            else:
                                tmpRow['dependencies'].append({"positive": -1, "negative": -1})
                        data['rows'].append(tmpRow)
            else:
                numbers = [int(x) for x in list(filter(lambda x: x != '', line.strip().split(' ')))[:-1]]
                if not numbers:
                    continue
                if not data['rows']:
                    continue

                # MaxSat matrix (pomijamy wagę lub nie? W Twoim kodzie nie było 'del numbers[0]')
                # Jeśli chcesz pominąć wagę, odkomentuj: del numbers[0]

                # --- INNER LOOP PROTECTION ---
                inner_counter = 0
                for n1 in numbers:
                    for n2 in numbers:
                        inner_counter += 1
                        # Sprawdzamy co 10k operacji wewnątrz macierzy
                        if inner_counter % 10000 == 0:
                            if time.time() - last_check_time > 1.0:
                                check_interruption(js_id, {
                                    'index': index,
                                    'data_snapshot': data
                                })
                                last_check_time = time.time()

                        if n1 == n2:
                            continue
                        if n1 > 0:
                            data['rows'][abs(n1) - 1]['dependencies'][abs(n2) - 1]['positive'] += 1
                        else:
                            data['rows'][abs(n1) - 1]['dependencies'][abs(n2) - 1]['negative'] += 1

    obj.content = json.dumps(data)
    obj.status = 'done'
    obj.progress = 'Progress: 100.0%'
    obj.save()


@app.task()
def create_maxsat_vis_tree(obj_id, js_id, js_format, selected_vars, resume_state=None):
    print("MAXSAT_VIS_TREE")

    obj = JsonFile.objects.get(id=js_id)

    if not resume_state:
        obj.status = 'pending'
        obj.save()

    data = {
        "info": None,
        "nodes": [],
        "edges": []
    }

    formulas = []
    start_index = 0
    parsing_done = False

    if resume_state:
        print(f"Resuming MAXSAT_VIS_TREE from line {resume_state.get('index')}")
        formulas = resume_state.get('formulas', [])
        start_index = resume_state.get('index', 0)
        parsing_done = resume_state.get('parsing_done', False)
        data['info'] = resume_state.get('info_data')

    text_file = TextFile.objects.get(id=obj_id)
    last_check_time = time.time()
    
    if not parsing_done:
        with open(text_file.content.path) as f:
            text = File(f)
            lines_amount = get_lines_amount_for(f)
            f.seek(0)

            if start_index > 0:
                for _ in range(start_index):
                    next(f, None)

            for index, line in enumerate(f, start=start_index):
                
                # --- TIME CHECK ---
                current_time = time.time()
                if current_time - last_check_time > 1.0:
                    update_progress(index, lines_amount, obj)
                    check_interruption(js_id, {
                        'formulas': formulas,
                        'index': index,
                        'parsing_done': False,
                        'info_data': data.get('info')
                    })
                    last_check_time = current_time

                if is_comment(line):
                    continue
                if is_info(line):
                    data['info'] = get_info_array(line)
                else:
                    formulas.append(get_numbers(line))
        
        parsing_done = True
        check_interruption(js_id, {
            'formulas': formulas,
            'index': 0,
            'parsing_done': True,
            'info_data': data.get('info')
        })

    obj.progress = 'Building Formula Tree...'
    obj.save()

    if formulas:
        # Checkpoint przed budową drzewa
        check_interruption(js_id, {'formulas': formulas, 'parsing_done': True, 'info_data': data.get('info')})
        
        tree = FormulaTree(formulas, 0)
        tree.serialize()
        data['nodes'] = tree.nodes
        data['edges'] = tree.edges

    obj.content = json.dumps(data)
    obj.status = 'done'
    obj.progress = 'Progress: 100.0%'
    obj.save()

@app.task()
def create_maxsat_vis_resolution(obj_id, js_id, js_format, selected_vars, resume_state=None):
    print("MAXSAT_VIS_RESOLUTION")
    obj = JsonFile.objects.get(id=js_id)

    if not resume_state:
        obj.status = 'pending'
        obj.save()

    data = {
        "info": None,
        "nodes": [],
        "edges": []
    }

    clause_weights = {}
    edges_tmp = {}
    variables = {}
    clause = 0
    start_index = 0
    parsing_done = False

    if resume_state:
        print(f"Resuming MAXSAT_VIS_RESOLUTION from line {resume_state.get('index')}")
        
        raw_weights = resume_state.get('clause_weights', {})
        clause_weights = {int(k): v for k, v in raw_weights.items()}

        raw_vars = resume_state.get('variables', {})
        variables = {int(k): v for k, v in raw_vars.items()}

        edges_tmp = restore_tuple_keys(resume_state.get('edges_tmp', {}))

        clause = resume_state.get('clause', 0)
        start_index = resume_state.get('index', 0)
        parsing_done = resume_state.get('parsing_done', False)
        data['info'] = resume_state.get('info_data')

    text_file = TextFile.objects.get(id=obj_id)
    
    # --- Dławik ---
    last_check_time = time.time()
    
    # --- FAZA 1: PARSOWANIE ---
    if not parsing_done:
        with open(text_file.content.path) as f:
            text = File(f)
            lines_amount = get_lines_amount_for(f)
            f.seek(0)

            if start_index > 0:
                for _ in range(start_index):
                    next(f, None)

            for index, line in enumerate(f, start=start_index):

                # --- TIME CHECK ---
                current_time = time.time()
                if current_time - last_check_time > 1.0:
                    update_progress(index, lines_amount, obj)
                    check_interruption(js_id, {
                        'clause_weights': clause_weights,
                        'variables': variables,
                        'clause': clause,
                        'index': index,
                        'parsing_done': False,
                        'info_data': data.get('info')
                    })
                    last_check_time = current_time

                if line.startswith('c') or line.startswith('C') or line in ['', ' ']:
                    continue
                if line.startswith('p'):
                    data['info'] = line.replace("\n", "").split(' ')
                else:
                    numbers = [int(x) for x in list(filter(lambda x: x != '', line.strip().split(' ')))[:-1]]
                    if not numbers:
                        continue
                    clause += 1
                    
                    clause_weights[clause] = numbers[0]
                    del numbers[0]

                    for n in numbers:
                        if n not in variables and (selected_vars is None or len(
                                selected_vars) == 0 or n in selected_vars or -n in selected_vars):
                            variables[n] = []
                        if n in variables:
                            variables[n].append(clause)
        
        parsing_done = True
        check_interruption(js_id, {
            'clause_weights': clause_weights,
            'variables': variables,
            'clause': clause,
            'index': 0,
            'parsing_done': True,
            'info_data': data.get('info')
        })

    # --- FAZA 2: GENEROWANIE KRAWĘDZI ---
    obj.progress = 'Generating Resolution Edges...'
    obj.save()
    
    # Używamy czasu zamiast modulo w pętli
    for v, clause_list_1 in variables.items():
        
        # --- TIME CHECK (PHASE 2) ---
        current_time = time.time()
        if current_time - last_check_time > 1.0:
             check_interruption(js_id, {
                'clause_weights': clause_weights,
                'variables': variables,
                'edges_tmp': edges_tmp,
                'clause': clause,
                'parsing_done': True,
                'info_data': data.get('info')
            })
             last_check_time = current_time

        if v < 0:
            continue
        if -v in variables.keys():
            clause_list_2 = variables[-v]

            for c1 in clause_list_1:
                for c2 in clause_list_2:
                    edges_tmp[(c1, c2)] = {"from": c1, "to": c2}

    if clause_weights:
        min_cw = min(clause_weights.values())
        max_cw = max(clause_weights.values())
        data['nodes'] = [get_node(c, cw, min_cw, max_cw) for c, cw in clause_weights.items()]
    else:
        data['nodes'] = []
        
    data['edges'] = [v for k, v in edges_tmp.items()]

    obj.content = json.dumps(data)
    obj.status = 'done'
    obj.progress = 'Progress: 100.0%'
    obj.save()


def get_node(clause, clause_weight, min_cw, max_cw):
    return {"id": clause, "color": {"background": get_clause_color(clause_weight, min_cw, max_cw)},
            "label": 'C_{}'.format(abs(clause))}


def get_clause_color(cw, min_cw, max_cw):
    normalized_cw = normalize_value(cw, min_cw, max_cw)
    return "rgba(255, {}, {})".format(normalized_cw, normalized_cw)


def normalize_value(v, min_v, max_v):
    return int((v - min_v) * 255 / (max_v - min_v))


def is_comment(line):
    if line.startswith('c') or line.startswith('C') or line in ['', ' ']:
        return True
    return False


def is_info(line):
    if line.startswith('p'):
        return True
    return False


def get_info_array(line):
    return line.split(' ')


def get_numbers(line):
    return [int(x) for x in list(filter(lambda x: x != '', line.strip().split(' ')))[:-1]]


def join_lists(lst):
    result = []
    [result.extend(el) for el in lst]
    return result


def most_common(lst):
    if not lst or lst == [[]]:
        return None
    joined = join_lists(lst)
    return max(joined, key=joined.count)


def get_lines_amount_for(file):
    linesAmount = 0
    for line in file:
        linesAmount += 1
    return linesAmount


def update_progress(index, linesAmount, obj):
    progress = float(index) / float(linesAmount) * float(100)
    obj.progress = "Progress: " + str(round(progress, 2)) + "%"
    obj.save()


class FormulaNode(object):
    def __init__(self, formula_list, level):
        self.children = []
        self.id = str(uuid.uuid4())
        self.level = level

        self.data = most_common(formula_list)
        self.formula_list = formula_list

        for formula in self.formula_list:
            formula.remove(self.data)

        [self.add_child(child) for child in FormulaTree(formula_list, level + 1).roots]

    def add_child(self, obj):
        self.children.append(obj)

    def set_level(self, level):
        self.level = level

    def set_id(self, id):
        self.id = id


class FormulaTree(object):
    def __init__(self, formula_list, start_level):
        self.nodes = []
        self.edges = []

        self.roots = []
        self.grouped_formula = []
        self.formula_list = self.group_formulas(formula_list)

        for formula in self.grouped_formula:
            if (formula != [[]]):
                self.roots.append(FormulaNode(formula, start_level))

    def group_formulas(self, lst):
        formulas = []
        tmp = []
        f = []
        root = most_common(lst)
        if not root:
            return formulas
        for formula in lst:
            if root in formula:
                f.append(formula)
            else:
                tmp.append(formula)
        self.grouped_formula.append(f)
        return self.group_formulas(tmp)

    def serialize(self):
        q = queue.Queue()

        for root in self.roots:
            q.put(root)

        for root in self.roots:
            root.set_level(0)

        while not q.empty():
            node = q.get()
            for child in node.children:
                self.edges.append({"from": node.id, "to": child.id, "color": {"color": '#ff383f'}})
                q.put(child)

            self.nodes.append({"id": node.id, "label": str(node.data), "level": node.level})


def rgb2hex(rgb):
    return '#%02x%02x%02x' % (tuple(int(value * 255) for value in rgb)[0:-1])


@app.task()
def run_visualization(obj_id, js_id, js_format, selected_vars):
    from profiles.tasks import create_json
    create_json(obj_id, js_id, js_format, selected_vars)
