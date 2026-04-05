import { ComponentFixture, TestBed } from '@angular/core/testing';
import { NO_ERRORS_SCHEMA } from '@angular/core';
import { provideRouter } from '@angular/router';
import { Sidebar } from './sidebar';

describe('Sidebar', () => {
  let component: Sidebar;
  let fixture: ComponentFixture<Sidebar>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Sidebar],
      providers: [provideRouter([])],
      schemas: [NO_ERRORS_SCHEMA],
    }).compileComponents();

    fixture = TestBed.createComponent(Sidebar);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('toggle_when_hidden_shows_sidebar', () => {
    // Arrange — visible starts as false (default)

    // Act
    component.toggle();

    // Assert
    expect(component['visible']).toBe(true);
  });

  it('toggle_when_visible_hides_sidebar', () => {
    // Arrange
    component['visible'] = true;

    // Act
    component.toggle();

    // Assert
    expect(component['visible']).toBe(false);
  });
});
