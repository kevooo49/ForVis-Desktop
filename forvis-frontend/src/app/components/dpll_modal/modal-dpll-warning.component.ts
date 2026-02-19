import { Component } from '@angular/core';
import { NgbActiveModal } from '@ng-bootstrap/ng-bootstrap';

@Component({
  selector: 'app-modal-dpll-warning',
  templateUrl: './modal-dpll-warning.component.html'
})
export class ModalDpllWarningComponent {
  constructor(public activeModal: NgbActiveModal) {}
}