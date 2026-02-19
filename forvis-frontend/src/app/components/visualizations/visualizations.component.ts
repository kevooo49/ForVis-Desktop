import { Component, Inject, OnInit } from '@angular/core';
import { NgbModal } from '@ng-bootstrap/ng-bootstrap';
import { Router } from '@angular/router';
import { Jsonfile } from '../../model/jsonFile';
import { ModalProgressComponent } from '../modal-progress/modal-progress.component';
import { ALERT_SERVICE, IAlertService } from '../../services/interfaces/alert-service';
import { AUTH_SERVICE, IAuthService } from '../../services/interfaces/auth-service';
import { IJsonFileService, JSON_FILE_SERVICE } from '../../services/interfaces/json-file-service';
import {NgForOf, NgIf, NgClass} from "@angular/common";

const formats = new Map<string, string>([
    ["sat_vis_factor", "visualization-vis_factor"],
    ["sat_vis_interaction", "visualization-vis_interaction"],
    ["sat_vis_matrix", "visualization-vis_matrix"],
    ["sat_vis_tree", "visualization-vis_tree"],
    ["sat_vis_cluster", "visualization-vis_cluster"],
    ["sat_vis_resolution", "visualization-vis_resolution"],
    ["sat_vis_distribution", "visualization-vis_distribution"],
    ["sat_vis_directed", "visualization-vis_directed"],
    ["sat_vis_2clause", "visualization-vis_2clause"],
    ["sat_vis_dpll", "visualization-vis_dpll"],
    ["sat_vis_cdcl", "visualization-vis_cdcl"],
    ["sat_vis_what_if", "visualization-vis_what_if"],
    ["sat_vis_heatmap", "visualization-vis-heatmap"],
    ["sat_vis_hypergraph", "visualization-vis_hypergraph"],
    ["sat_vis_landscape", "visualization-vis_landscape"],
    ["raw", "visualization-raw"],
    ["maxsat_vis_factor", "visualization-vis_factor"],
    ["maxsat_vis_interaction", "visualization-vis_interaction"],
    ["maxsat_vis_matrix", "visualization-vis_matrix"],
    ["maxsat_vis_tree", "visualization-vis_tree"],
    ["maxsat_vis_cluster", "visualization-vis_cluster"],
    ["maxsat_vis_resolution", "visualization-vis_resolution"],
    ["maxsat_vis_distribution", "visualization-vis_distribution"],
    ["community", "visualization-vis-community"]
]);

const formatsNames = new Map<string, string>([
    ["sat_vis_factor", "SAT Factor Graph"],
    ["sat_vis_interaction", "SAT Interaction Graph"],
    ["sat_vis_matrix", "SAT Matrix Visualization"],
    ["sat_vis_tree", "SAT Tree Visualization"],
    ["sat_vis_cluster", "SAT Cluster Visualization"],
    ["sat_vis_resolution", "SAT Resolution Graph"],
    ["sat_vis_distribution", "SAT Distribution Chart"],
    ["sat_vis_directed", "SAT Direct Graphical Model"],
    ["sat_vis_2clause", "SAT 2-Clauses Interaction Graph"],
    ["sat_vis_dpll", "SAT DPLL Solver Visualization"],
    ["sat_vis_cdcl", "SAT CDCL Solver Visualization"],
    ["sat_vis_what_if", "SAT What if... Visualization"],
    ["sat_vis_heatmap", "SAT heatmap visualization"],
    ["sat_vis_hypergraph", "SAT hypergraph visualization"],
    ["sat_vis_landscape", "SAT Landscape Chart"],
    ["raw", "Raw File Visualization"],
    ["maxsat_vis_factor", "MAX-SAT Factor Graph"],
    ["maxsat_vis_interaction", "MAX-SAT Interaction Graph"],
    ["maxsat_vis_matrix", "MAX-SAT Matrix Visualization"],
    ["maxsat_vis_tree", "MAX-SAT Tree Visualization"],
    ["maxsat_vis_cluster", "MAX-SAT Cluster Visualization"],
    ["maxsat_vis_resolution", "MAX-SAT Resolution Graph"],
    ["maxsat_vis_distribution", "MAX-SAT Distribution Chart"],
    ["community", "Communities"]
]);

@Component({
    selector: 'app-visualizations',
    templateUrl: './visualizations.component.html',
    imports: [
        NgIf,
        NgForOf,
        NgClass
    ],
    styleUrls: ['./visualizations.component.css']
})
export class VisualizationsComponent implements OnInit {
    visualizations: Jsonfile[] = [];
    isLoading = true;

    pausingIds = new Set<number>();
    resumingIds = new Set<number>();

    constructor(
        @Inject(ALERT_SERVICE) private alertService: IAlertService,
        @Inject(AUTH_SERVICE) private authService: IAuthService,
        @Inject(JSON_FILE_SERVICE) private jsonFileService: IJsonFileService,
        private modalService: NgbModal,
        private router: Router
    ) {}

    ngOnInit() {
        this.updateList();
        setInterval(() => this.updateList(), 2000);
    }

    // updateList(): void {
    //     this.jsonFileService.getJsonFileList().subscribe({
    //         next: (data: Jsonfile[]) => {
    //             this.visualizations = data.sort((a, b) => b.id - a.id); // newest first
    //             this.isLoading = false;
    //         },
    //         error: (error) => this.alertService.error(error)
    //     });
    // }

    updateList(): void {
        this.jsonFileService.getJsonFileList().subscribe({
            next: (data: Jsonfile[]) => {
                this.visualizations = data.sort((a, b) => b.id - a.id);
                
                // NOWE: Czyszczenie flag lokalnych
                this.visualizations.forEach(vis => {
                    // Jeśli backend już potwierdził PAUSED, usuwamy z listy "oczekujących na pauzę"
                    if (vis.status === 'paused' && this.pausingIds.has(vis.id)) {
                        this.pausingIds.delete(vis.id);
                    }
                    // Jeśli backend potwierdził PENDING (po wznowieniu), usuwamy z listy "oczekujących na wznowienie"
                    if (vis.status === 'pending' && this.resumingIds.has(vis.id)) {
                        this.resumingIds.delete(vis.id);
                    }
                });

                this.isLoading = false;
            },
            error: (error) => this.alertService.error(error)
        });
    }

    checkProgress(vis: Jsonfile): void {
        const modalRef = this.modalService.open(ModalProgressComponent, { centered: true });
        modalRef.componentInstance.progressMessage = vis.progress;
    }

    deleteVisualization(id: number): void {
        this.jsonFileService.deleteJsonFile(id).subscribe({
            next: () => this.updateList(),
            error: (error) => this.alertService.error(error)
        });
    }

    // pauseVisualization(vis: Jsonfile): void {
    //     this.jsonFileService.pauseJsonFile(vis.id).subscribe({
    //         next: () => {
    //             this.updateList(); 
    //         },
    //         error: (error) => this.alertService.error('Failed to pause: ' + error)
    //     });
    // }

    pauseVisualization(vis: Jsonfile): void {
        // 1. Natychmiast dodajemy do listy "Zatrzymywanie..."
        this.pausingIds.add(vis.id);

        this.jsonFileService.pauseJsonFile(vis.id).subscribe({
            next: () => {
                // Po wysłaniu requestu nie robimy nic, czekamy aż updateList() 
                // otrzyma status 'paused' z bazy danych.
                console.log('Pause signal sent for ' + vis.id);
            },
            error: (error) => {
                this.alertService.error('Failed to pause: ' + error);
                // W razie błędu usuwamy flagę, żeby odblokować przycisk
                this.pausingIds.delete(vis.id);
            }
        });
    }

    // resumeVisualization(vis: Jsonfile): void {
    //     this.jsonFileService.resumeJsonFile(vis.id).subscribe({
    //         next: () => {
    //             this.updateList();
    //         },
    //         error: (error) => this.alertService.error('Failed to resume: ' + error)
    //     });
    // }  
    
    resumeVisualization(vis: Jsonfile): void {
        // 1. Natychmiast dodajemy do listy "Wznawianie..."
        this.resumingIds.add(vis.id);

        this.jsonFileService.resumeJsonFile(vis.id).subscribe({
            next: () => {
                console.log('Resume signal sent for ' + vis.id);
                // Tu opcjonalnie możemy wymusić szybki update
                this.updateList();
            },
            error: (error) => {
                this.alertService.error('Failed to resume: ' + error);
                this.resumingIds.delete(vis.id);
            }
        });
    }

    visualize(vis: Jsonfile): void {
        const route = formats.get(vis.json_format);
        if (!route) {
            this.alertService.error('Unsupported format: ' + vis.json_format);
            return;
        }

        // Extract the kind from the json_format (sat or maxsat)
        const kind = vis.json_format.split('_')[0];
        
        // Log the navigation details for debugging
        console.log('Navigating to visualization:', {
            route: route,
            id: vis.id,
            name: vis.name,
            kind: kind
        });
        
        // Use the router to navigate to the visualization
        this.router.navigate([route, vis.id, vis.name, kind]);
    }

    visualizeCommunity(vis: Jsonfile): void {
        this.jsonFileService.visualizeCommunity(vis);
        const currentUrl = this.router.url;
        this.router.navigateByUrl('/', { skipLocationChange: true }).then(() => {
            this.router.navigate([currentUrl]);
        });
        this.updateList();
    }

    isDone(vis: Jsonfile): boolean {
        return vis.status === 'done' || vis.status === 'error' || vis.progress === 'Progress: 100.0%';
    }

    isPaused(vis: Jsonfile): boolean {
        return vis.status === 'paused';
    }

    isPausing(vis: Jsonfile): boolean {
        return this.pausingIds.has(vis.id);
    }

    isResuming(vis: Jsonfile): boolean {
        return this.resumingIds.has(vis.id);
    }

    canCreateCommunity(vis: Jsonfile): boolean {
        const allowedFormats = [
            'sat_vis_factor', 'sat_vis_interaction', 'sat_vis_tree',
            'maxsat_vis_factor', 'maxsat_vis_interaction', 'maxsat_vis_tree'
        ];
        return allowedFormats.includes(vis.json_format);
    }

    getFormat(json_format: string): string {
        if (json_format.startsWith("community")) {
            return 'Community Graph';
        }
        return formatsNames.get(json_format) || json_format;
    }
}