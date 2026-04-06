import { Routes } from '@angular/router';
import { authGuard, unauthenticatedGuard, setupGuard } from './auth/auth.guard';

export const routes: Routes = [
  {
    path: 'setup',
    loadComponent: () => import('./auth/setup').then((m) => m.Setup),
    canActivate: [setupGuard],
  },
  {
    path: 'login',
    loadComponent: () => import('./auth/login').then((m) => m.Login),
    canActivate: [unauthenticatedGuard],
  },
  {
    path: '',
    loadComponent: () => import('./layout/layout').then((m) => m.Layout),
    canActivate: [authGuard],
    children: [
      {
        path: 'dashboard',
        loadComponent: () => import('./dashboard/dashboard').then((m) => m.Dashboard),
      },
      {
        path: 'accounts',
        loadComponent: () => import('./accounts/accounts').then((m) => m.Accounts),
      },
      {
        path: 'categories',
        loadComponent: () => import('./categories/categories').then((m) => m.Categories),
      },
      {
        path: '',
        redirectTo: 'dashboard',
        pathMatch: 'full',
      },
    ],
  },
  {
    path: '**',
    redirectTo: '',
  },
];
