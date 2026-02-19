import { Inject, Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { AUTH_SERVICE, IAuthService } from "../interfaces/auth-service";
import { IFileService } from "../interfaces/file-service";


import { Environment } from '../../../environments/environment';

@Injectable({
  providedIn: 'root'
})
export class FileService implements IFileService {

  private base = Environment.baseUrl;

  // SAT
  private url_sat_files     = `${this.base}/profile/files/sat/`;
  private url_sat_file      = `${this.base}/profile/file/sat/`;

  // MAX-SAT
  private url_maxsat_files  = `${this.base}/profile/files/maxsat/`;
  private url_maxsat_file   = `${this.base}/profile/file/maxsat/`;

  // VIS 2-CLAUSE
  private url_vis_2clause_files = `${this.base}/profile/files/vis_2clause/`;
  private url_vis_2clause_file  = `${this.base}/profile/file/vis_2clause/`;

  constructor(
    private http: HttpClient,
    @Inject(AUTH_SERVICE) private authService: IAuthService
  ) {}

  // ---------- SAT ----------
  getSatFilesList(): Observable<any> {
    return this.http.get(this.url_sat_files, this.authService.authOptions());
  }

  getSatFile(id: number, format: string, selectedVariables: string[] = []): Observable<any> {
    let params = new HttpParams();

    if (selectedVariables.length > 0) {
      params = params.set('selectedVariables', selectedVariables.join(','));
    }

    return this.http.get(`${this.url_sat_file}${id}/${format}/`, {
      ...this.authService.authOptions(),
      params
    });
  }

  deleteSatFile(id: number): Observable<any> {
    return this.http.delete(`${this.url_sat_file}${id}/del/`, this.authService.authOptions());
  }

  // ---------- MAX-SAT ----------
  getMaxSatFilesList(): Observable<any> {
    return this.http.get(this.url_maxsat_files, this.authService.authOptions());
  }

  getMaxSatFile(id: number, format: string, selectedVariables: string[] = []): Observable<any> {
    let params = new HttpParams();

    if (selectedVariables.length > 0) {
      params = params.set('selectedVariables', selectedVariables.join(','));
    }

    return this.http.get(`${this.url_maxsat_file}${id}/${format}/`, {
      ...this.authService.authOptions(),
      params
    });
  }

  deleteMaxSatFile(id: number): Observable<any> {
    return this.http.delete(`${this.url_maxsat_file}${id}/del/`, this.authService.authOptions());
  }

  // ---------- VIS 2-CLAUSE ----------
  getVis2ClauseFilesList(): Observable<any> {
    return this.http.get(this.url_vis_2clause_files, this.authService.authOptions());
  }

  getVis2ClauseFile(id: number, format: string): Observable<any> {
    return this.http.get(`${this.url_vis_2clause_file}${id}/${format}/`, this.authService.authOptions());
  }

  deleteVis2ClauseFile(id: number): Observable<any> {
    return this.http.delete(`${this.url_vis_2clause_file}${id}/del/`, this.authService.authOptions());
  }
}
