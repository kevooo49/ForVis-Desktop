import { Component, Inject } from '@angular/core';
import { Router, ActivatedRoute } from '@angular/router';
import { User } from '../../model/user';
import { ALERT_SERVICE, IAlertService } from '../../services/interfaces/alert-service';
import { AUTH_SERVICE, IAuthService } from '../../services/interfaces/auth-service';
import {FormsModule} from '@angular/forms';
import {NgIf} from '@angular/common';
import {Authentication} from '../../model/authentication';

@Component({
  selector: 'app-login',
  templateUrl: './login.component.html',
  imports: [
    FormsModule,
    NgIf
  ],
  styleUrls: ['./login.component.css']
})
export class LoginComponent {
  user: Authentication = {
    username: '',
    password: ''
  };

  errorMessage: string | null = null;

  constructor(
    @Inject(AUTH_SERVICE) private authService: IAuthService,
    @Inject(ALERT_SERVICE) private alertService: IAlertService,
    private router: Router,
    private route: ActivatedRoute) { }

  // login(): void {
  //   const returnUrl = this.route.snapshot.queryParams['returnUrl'] || '/cnf-uploader';

  //   this.authService.tokenAuth(this.user).subscribe({
  //     next: (response) => {
  //       if (response && response.token) {
  //         console.log('Login successful');
  //         this.router.navigateByUrl(returnUrl);
  //       } else {
  //         this.alertService.error('Invalid username or password');
  //       }
  //     },
  //     error: (error) => {
  //       console.error('Login error:', error);
  //       this.alertService.error('Login failed. Please check your credentials.');
  //     }
  //   });
  // }

  login(): void {

    this.errorMessage = null;

    const returnUrl = this.route.snapshot.queryParams['returnUrl'] || '/cnf-uploader';

    this.authService.tokenAuth(this.user).subscribe({
      next: (response) => {
        if (response && response.token) {
          console.log('Login successful');
          this.router.navigateByUrl(returnUrl);
        } else {
          this.errorMessage = "The username and password you entered don't match any account.";
        }
      },
      error: (error) => {
        console.error('Login error:', error);

        if (error.status === 400 || error.status === 401) {
          this.errorMessage = "The username and password you entered don't match any account.";
        } else {
          this.errorMessage = "Login failed. Please try again later.";
        }
      }
    });
  }


  goToRegistration(): void {
    this.router.navigate(['register']).then(() => {
      console.log('Navigated to registration page!');
    }).catch(error => {
      console.error('Navigation failed', error);
    });
  }
}