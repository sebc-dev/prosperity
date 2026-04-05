import { ComponentFixture, TestBed } from '@angular/core/testing';
import { NO_ERRORS_SCHEMA } from '@angular/core';
import { provideRouter } from '@angular/router';
import { Sidebar } from './sidebar';

describe('Sidebar', () => {
  let fixture: ComponentFixture<Sidebar>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Sidebar],
      providers: [provideRouter([])],
      schemas: [NO_ERRORS_SCHEMA],
    }).compileComponents();

    fixture = TestBed.createComponent(Sidebar);
    fixture.detectChanges();
  });

  it('renders_navigation_link_to_accounts', () => {
    // Arrange
    const compiled = fixture.nativeElement as HTMLElement;

    // Act — component already rendered in beforeEach

    // Assert
    const link = compiled.querySelector('a[routerLink="/accounts"]');
    expect(link).toBeTruthy();
  });
});
