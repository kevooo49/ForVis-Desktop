import { Component, OnInit, inject, signal, ViewChild, ElementRef } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { Chart, ChartConfiguration, ScatterController, PointElement, LinearScale, Title, Tooltip, Legend, ScriptableContext, ChartTypeRegistry } from 'chart.js';
import { CommonModule } from '@angular/common';
import html2canvas from 'html2canvas';

import { FileService } from '../../services/file-service/file.service';
import { AlertService } from '../../services/alert-service/alert.service';
import type { File } from '../../models/file';
import { DownloadableComponent } from '../visualization-download/visualization-download.component';
import { JsonFileService } from '../../services/json-file-service/json-file.service';
import { JSON_FILE_SERVICE, IJsonFileService } from '../../services/interfaces/json-file-service';

// Register the scatter controller and required elements for Chart.js
Chart.register(ScatterController, PointElement, LinearScale, Title, Tooltip, Legend);

interface VisualizationContent {
  points: ScatterPoint[];
  path: PathPoint[];
  options?: any;
}
interface PathPoint{
    x: number, 
    y: number
}
interface VisualizationData {
  content: VisualizationContent;
}
interface ScatterPoint {
  x: number;
  y: number;
  cost: number;
}

@Component({
  selector: 'app-visualization-vis_landscape',
  templateUrl: './visualization-vis_landscape.component.html',
  styleUrls: ['./visualization-vis_landscape.component.css'],
  standalone: true,
  imports: [CommonModule],
  providers: [
    { provide: JSON_FILE_SERVICE, useClass: JsonFileService },
    FileService,
    AlertService
  ]
})
export class VisualizationVisLandscapeComponent extends DownloadableComponent implements OnInit {
  @ViewChild('visualization') private visElement!: ElementRef<HTMLCanvasElement>;

  private route = inject(ActivatedRoute);
  private fileService = inject(FileService);
  private alertService = inject(AlertService);
  private jsonFileService = inject(JSON_FILE_SERVICE) as IJsonFileService;

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

  public visualization: Chart | null = null;
  errorMessage: string | null = null;
  private readonly errorMessageDefault = 'An overload occurred during processing your file. Please try again with other method or file.';

  ngOnInit() {
    this.route.params.subscribe(params => {
      this.fileId.set(params['f']);
      this.fileName.set(params['name']);
      this.kind.set(params['kind']);
      this.loadVis();
    });
  }

  loadVis() {
    this.loading.set(true);
    this.jsonFileService.getJsonFile(this.fileId(), this.kind(), []).subscribe({
      next: (data: any) => {
        console.log('Landscape backend response:', data);
        this.info.set(null);
        // Accept both {datasets: ...} and {content: {datasets: ...}}
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

        const canvas = this.visElement?.nativeElement;
        if (!canvas) {
          this.alertService.error('Visualization canvas not found');
          return;
        }

        // Destroy existing chart if it exists
        if (this.visualization) {
          this.visualization.destroy();
        }

        // const config: ChartConfiguration = {
        //     type: 'scatter',
        //     data: {
        //         datasets: [{
        //             label: 'Krajobraz Formuły',
        //             data: data.content.points as ScatterPoint[],
        //             pointBackgroundColor: (context: ScriptableContext<any>) => {
        //                 const point = context.raw as ScatterPoint;
        //                 if (!point?.cost) return 'rgba(0,0,0,0.1)';

        //                 const r = Math.floor(point.cost * 255);
        //                 const g = Math.floor((1 - point.cost) * 255);
        //                 return `rgb(${r}, ${g}, 0)`;
        //             },
        //             pointRadius: 5,
        //             pointHoverRadius: 8
        //         }]
        //     },
        //     options: {
        //         responsive: true,
        //         plugins: {
        //             legend: { display: false },
        //             tooltip: {
        //                 callbacks: {
        //                     label: (context) => {
        //                         const point = context.raw as ScatterPoint;
        //                         return `Koszt: ${(point.cost * 100).toFixed(2)}%`;
        //                     }
        //                 }
        //             }
        //         },
        //         scales: {
        //             x: { display: false },
        //             y: { display: false }
        //         }
        //     }
        // };
        const config: ChartConfiguration = {
  type: 'scatter',
  data: {
    datasets: [
      {
        label: 'Krajobraz Formuły',
        data: data.content.points as ScatterPoint[],
        pointBackgroundColor: (context: ScriptableContext<any>) => {
          const point = context.raw as ScatterPoint;
          if (!point?.cost && point?.cost !== 0) return 'rgba(0,0,0,0.1)';
          const r = Math.floor(point.cost * 255);
          const g = Math.floor((1 - point.cost) * 255);
          return `rgb(${r}, ${g}, 0)`;
        },
        pointRadius: 4,
        pointHoverRadius: 6,
        borderWidth: 0,
        order: 2
      },
      {
        type: 'line', 
        label: 'Ścieżka Solvera',
        data: data.content.path,
        fill: false,
        borderColor: 'rgba(0, 0, 255, 0.8)', 
        borderWidth: 2,
        pointRadius: 6, 
        pointBackgroundColor: 'blue',
        tension: 0.1,
        showLine: true,
        order: 1 
      }
    ]
  },
  options: {
                responsive: true,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (context) => {
                                const point = context.raw as ScatterPoint;
                                return `Koszt: ${(point.cost * 100).toFixed(2)}%`;
                            }
                        }
                    }
                },
                scales: {
                    x: { display: false },
                    y: { display: false }
                }
            }
};



        this.visualization = new Chart(canvas, config);
        this.errorMessage = null;
        this.loading.set(false);
      },
      error: (error: Error) => {
        this.errorMessage = this.errorMessageDefault;
        this.alertService.error(this.errorMessageDefault);
        console.error('Error loading visualization:', error);
        this.loading.set(false);
      }
    });
  }

  download() {
    // Implementation for downloading the visualization
    const element = document.getElementById('visualization');
    if (element) {
      html2canvas(element).then(canvas => {
        const link = document.createElement('a');
        link.download = 'visualization.png';
        link.href = canvas.toDataURL();
        link.click();
      });
    }
  }
}
