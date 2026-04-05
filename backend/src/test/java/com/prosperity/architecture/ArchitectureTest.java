package com.prosperity.architecture;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.classes;
import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;
import static com.tngtech.archunit.library.dependencies.SlicesRuleDefinition.slices;

import com.tngtech.archunit.junit.AnalyzeClasses;
import com.tngtech.archunit.junit.ArchTest;
import com.tngtech.archunit.lang.ArchRule;

/**
 * Architecture rules enforcing layered structure (D-02), banking abstraction (D-03), annotation
 * placement, and cross-package isolation.
 */
@AnalyzeClasses(packages = "com.prosperity")
class ArchitectureTest {

  // --- Existing rules ---

  @ArchTest
  static final ArchRule noCircularDependencies =
      slices()
          .matching("com.prosperity.(*)..")
          .should()
          .beFreeOfCycles()
          .as("Feature packages should be free of circular dependencies");

  @ArchTest
  static final ArchRule bankingTopLevelClassesShouldBeInterfacesOrRecords =
      classes()
          .that()
          .resideInAPackage("com.prosperity.banking")
          .should()
          .beInterfaces()
          .orShould()
          .beRecords()
          .as(
              "Banking top-level classes should be interfaces or records to enforce abstraction"
                  + " (D-03)");

  @ArchTest
  static final ArchRule sharedShouldNotDependOnFeaturePackages =
      noClasses()
          .that()
          .resideInAPackage("com.prosperity.shared..")
          .should()
          .dependOnClassesThat()
          .resideInAnyPackage(
              "com.prosperity.auth..",
              "com.prosperity.account..",
              "com.prosperity.transaction..",
              "com.prosperity.category..",
              "com.prosperity.envelope..",
              "com.prosperity.banking..")
          .as("Shared package should not depend on any feature packages");

  // --- Layered dependency rules ---

  @ArchTest
  static final ArchRule controllersShouldNotDependOnRepositories =
      noClasses()
          .that()
          .haveSimpleNameEndingWith("Controller")
          .and()
          .resideOutsideOfPackage("com.prosperity.auth..")
          .should()
          .dependOnClassesThat()
          .haveSimpleNameEndingWith("Repository")
          .as(
              "Controllers (outside auth) should not depend on Repository classes"
                  + " — use Services instead");

  @ArchTest
  static final ArchRule repositoriesShouldNotDependOnControllersOrServices =
      noClasses()
          .that()
          .haveSimpleNameEndingWith("Repository")
          .and()
          .resideInAnyPackage("com.prosperity..")
          .should()
          .dependOnClassesThat()
          .haveSimpleNameEndingWith("Controller")
          .orShould()
          .dependOnClassesThat()
          .haveSimpleNameEndingWith("Service")
          .as("Repositories should not depend on Controllers or Services");

  @ArchTest
  static final ArchRule authShouldNotDependOnFeaturePackages =
      noClasses()
          .that()
          .resideInAPackage("com.prosperity.auth..")
          .should()
          .dependOnClassesThat()
          .resideInAnyPackage(
              "com.prosperity.account..",
              "com.prosperity.transaction..",
              "com.prosperity.category..",
              "com.prosperity.envelope..")
          .as("Auth package should not depend on feature packages (account, transaction, etc.)");

  @ArchTest
  static final ArchRule bankingShouldNotDependOnFeaturePackages =
      noClasses()
          .that()
          .resideInAPackage("com.prosperity.banking..")
          .should()
          .dependOnClassesThat()
          .resideInAnyPackage(
              "com.prosperity.auth..",
              "com.prosperity.account..",
              "com.prosperity.transaction..",
              "com.prosperity.category..",
              "com.prosperity.envelope..")
          .as("Banking package should not depend on any feature packages");

  // --- Annotation placement rules ---

  @ArchTest
  static final ArchRule controllersShouldBeAnnotatedWithRestController =
      classes()
          .that()
          .haveSimpleNameEndingWith("Controller")
          .and()
          .resideInAnyPackage("com.prosperity..")
          .should()
          .beAnnotatedWith("org.springframework.web.bind.annotation.RestController")
          .as("Controller classes should be annotated with @RestController");

  @ArchTest
  static final ArchRule servicesShouldBeAnnotatedWithService =
      classes()
          .that()
          .haveSimpleNameEndingWith("Service")
          .and()
          .resideInAnyPackage("com.prosperity..")
          .and()
          .areNotInterfaces()
          .should()
          .beAnnotatedWith("org.springframework.stereotype.Service")
          .as("Service classes should be annotated with @Service");

  @ArchTest
  static final ArchRule repositoriesShouldBeInterfaces =
      classes()
          .that()
          .haveSimpleNameEndingWith("Repository")
          .and()
          .resideInAnyPackage("com.prosperity..")
          .should()
          .beInterfaces()
          .as("Repository classes should be interfaces (Spring Data repositories)");
}
