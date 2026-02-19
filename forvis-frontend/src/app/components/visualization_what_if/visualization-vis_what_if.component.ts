import { Component, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { Network, Node, Edge } from 'vis-network';
import { DataSet } from 'vis-data';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

import { FileService } from '../../services/file-service/file.service';
import { AlertService } from '../../services/alert-service/alert.service';
import type { File } from '../../models/file';
import { DownloadableComponent } from '../visualization-download/visualization-download.component';
import { JsonFileService } from '../../services/json-file-service/json-file.service';
import { JSON_FILE_SERVICE } from '../../services/interfaces/json-file-service';
import { ALERT_SERVICE } from '../../services/interfaces/alert-service';
import { FILE_SERVICE } from '../../services/interfaces/file-service';

interface VisualizationContent {
  variables: string[],
  nodes: { [varName: string]: { pos: Node[], neg: Node[] } };
  edges: { [varName: string]: { pos: Edge[], neg: Edge[] } };
  options: any;
}

interface VisualizationData {
  content: VisualizationContent;
}

interface Font {
  size: number;
  [key: string]: any;
}

@Component({
  selector: 'app-visualization-vis_what_if',
  templateUrl: './visualization-vis_what_if.component.html',
  styleUrls: ['./visualization-vis_what_if.component.css'],
  standalone: true,
  imports: [CommonModule, FormsModule],
  providers: [
    { provide: JSON_FILE_SERVICE, useClass: JsonFileService },
    { provide: ALERT_SERVICE, useClass: AlertService },
    { provide: FILE_SERVICE, useClass: FileService }
  ]
})
export class VisualizationVisWhatIfComponent extends DownloadableComponent implements OnInit {
  private route = inject(ActivatedRoute);
  private fileService = inject(FileService);
  private alertService = inject(AlertService);
  private jsonFileService = inject(JSON_FILE_SERVICE);
  private router = inject(Router);
  fileId = signal<number>(0);
  fileName = signal<string>('');
  file = signal<File>({
    id: 0,
    name: '',
    content: null,
    type: '',
    size: 0,
    created_at: '',
    updated_at: '',
    user_id: 0
  });
  info = signal<string | null>(null);
  kind = signal<string>('');
  loading = signal<boolean>(false);
  stabilizationInProgress0 = signal<boolean>(false);
  stabilizationInProgress1 = signal<boolean>(false);
  public nodes0: DataSet<Node> | null = null;
  public edges0: DataSet<Edge> | null = null;
  public network0: Network | null = null;
  public nodes1: DataSet<Node> | null = null;
  public edges1: DataSet<Edge> | null = null;
  public network1: Network | null = null;
  public availableVariables = signal<string[]>([]);
  public selectedVariableId: string | null = null;
  private fullContent: VisualizationContent | null = null;

  private readonly errorMessage = 'An overload occurred during processing your file. Please try again with other method or file.';
  goBack(){
    this.router.navigate(["visualizations"]);
  }
  ngOnInit() {
  this.route.params.subscribe(params => {
    this.fileId.set(params['f']);
    this.fileName.set(params['name']);
    this.kind.set(params['kind']);
    this.allVariables();
  });
}

  startStab0() {
    if (this.network0) {
      this.network0.startSimulation();
    }
  }
  startStab1() {
    if (this.network1) {
      this.network1.startSimulation();
    }
  }

  stopStab0() {
    if (this.network0) {
      this.network0.stopSimulation();
      this.network0.fit();
    }
  }
  stopStab1() {
    if (this.network1) {
      this.network1.stopSimulation();
      this.network1.fit();
    }
  }
  allVariables(){
     this.jsonFileService.getJsonFile(this.fileId(), this.kind(), []).subscribe({
        next: (data: VisualizationData) => {
        this.info.set(null);
        this.file.set({
          id: this.fileId(),
          name: this.fileName(),
          content: data.content,
          type: this.kind(),
          size: 0,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          user_id: 0
        });
    if (data.content && data.content.variables) {
        this.availableVariables.set(data.content.variables);
        
        if (data.content.variables.length > 0) {
          this.selectedVariableId = String(data.content.variables[0]);
          this.loadVis();
        }
      }
    },
        error: (error: Error) => {
        this.alertService.error(this.errorMessage);
        console.error('Error loading variables:', error);
      }

     })
  }
  onVariableChange(event: any) {
    const varId = event.target.value;
    this.selectedVariableId = varId;
    this.loadVis();
    }
  loadVis() {
    this.jsonFileService.getJsonFile(this.fileId(), this.kind(), []).subscribe({
      next: (data: VisualizationData) => {
        this.info.set(null);
        this.file.set({
          id: this.fileId(),
          name: this.fileName(),
          content: data.content,
          type: this.kind(),
          size: 0,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          user_id: 0
        });
        if (!this.selectedVariableId) {
          return;
        }
        this.nodes0 = new DataSet(data.content.nodes[this.selectedVariableId].neg);
        this.edges0 = new DataSet(data.content.edges[this.selectedVariableId].neg);
        this.nodes1 = new DataSet(data.content.nodes[this.selectedVariableId].pos);
        this.edges1 = new DataSet(data.content.edges[this.selectedVariableId].pos);
        
        this.nodes0.forEach((node: Node) => {
          const font = node.font as Font;
          if (font && font.size < 1) {
            font.size = 1;
          }
        });
        this.nodes1.forEach((node: Node) => {
          const font = node.font as Font;
          if (font && font.size < 1) {
            font.size = 1;
          }
        });

        const container0 = document.getElementById('viz-false');
        const container1 = document.getElementById('viz-true');
        if (!container0 || !container1) {
          this.alertService.error('Visualization container not found');
          return;
        }

        const _data0 = {
          nodes: this.nodes0,
          edges: this.edges0
        };
        const _data1 = {
          nodes: this.nodes1,
          edges: this.edges1
        };
        
        const options = {
          edges: {
            smooth: false
          },
          physics: {
            enabled: true,
            barnesHut: {
              avoidOverlap: 1,
              centralGravity: 3.5
            },
            maxVelocity: 1,
            minVelocity: 1
          }
        };
        
        this.loading.set(true);
        this.network0 = new Network(container0, _data0, options);
        this.network1 = new Network(container1, _data1, options);
        this.stopStab0();
        this.stopStab1();

        if (this.network0) {
          this.network0.on("startStabilizing", () => {
            this.stabilizationInProgress0.set(true);
          });

          this.network0.on("stabilized", () => {
            this.stabilizationInProgress0.set(false);
          });

          this.network0.once("stabilizationIterationsDone", () => {
            this.stabilizationInProgress0.set(false);
          });
        }
        if (this.network1) {
          this.network1.on("startStabilizing", () => {
            this.stabilizationInProgress1.set(true);
          });

          this.network1.on("stabilized", () => {
            this.stabilizationInProgress1.set(false);
          });

          this.network1.once("stabilizationIterationsDone", () => {
            this.loading.set(false);
            this.stabilizationInProgress1.set(false);
          });
        }
      },
      error: (error: Error) => {
        this.alertService.error(this.errorMessage);
        console.error('Error loading visualization:', error);
      }
    });
  }
}