import { Inject, Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { AUTH_SERVICE, IAuthService } from '../interfaces/auth-service';
import { Jsonfile } from '../../model/jsonFile';
import { Environment } from '../../../environments/environment';
import { Observable } from 'rxjs';
import { IJsonFileService } from "../interfaces/json-file-service";
import { map } from 'rxjs/operators';

@Injectable()
export class JsonFileService implements IJsonFileService {

  private url_visualizations = `${Environment.baseUrl}/profile/visualizations`;
  // Zwróć uwagę: url_visualization kończy się na 'visualization/'
  private url_visualization = `${Environment.baseUrl}/profile/visualization/`; 
  private url_community = `${Environment.baseUrl}/profile/visualization/community/`;

  constructor(
      @Inject(AUTH_SERVICE) private authService: IAuthService,
      private http: HttpClient
  ) {}

  visualizeCommunity(vis: Jsonfile): void {
    this.http.get(`${this.url_community}${vis.id}/`, this.authService.authOptions())
        .subscribe(x => console.log(x));
  }

  getJsonFileList(): Observable<any> {
    return this.http.get(this.url_visualizations, this.authService.authOptions());
  }

  getJsonFile(id: number, format: string, selectedVariables: string[] = []): Observable<any> {
    const params = new HttpParams().set('selectedVariables', selectedVariables.join(','));
    const options = {
      ...this.authService.authOptions(),
      params
    };

    return this.http
      .get<any>(`${this.url_visualization}${id}/${format}/`, options)
      .pipe(
        map((resp: any) => {
          let content = resp.content;

          if (typeof content === 'string') {
            try {
              content = JSON.parse(content);
            } catch (e) {
              console.error('Nie udało się sparsować JSON z pola content:', e, content);
            }
          }

          return {
            ...resp,
            content
          };
        })
      );
  }

  deleteJsonFile(id: number): Observable<any> {
    return this.http.delete(`${this.url_visualization}${id}/del/`, this.authService.authOptions());
  }

  // --- NOWE METODY ---

  pauseJsonFile(id: number): Observable<any> {
    // Endpoint: /profile/visualization/pause/<id>/
    // Używamy POST, bo zmieniamy stan na serwerze
    return this.http.post(`${this.url_visualization}pause/${id}/`, {}, this.authService.authOptions());
  }

  resumeJsonFile(id: number): Observable<any> {
    // Endpoint: /profile/visualization/resume/<id>/
    return this.http.post(`${this.url_visualization}resume/${id}/`, {}, this.authService.authOptions());
  }
}