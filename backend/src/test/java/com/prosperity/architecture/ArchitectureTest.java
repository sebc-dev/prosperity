package com.prosperity.architecture;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.classes;
import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;
import static com.tngtech.archunit.library.dependencies.SlicesRuleDefinition.slices;

import com.tngtech.archunit.junit.AnalyzeClasses;
import com.tngtech.archunit.junit.ArchTest;
import com.tngtech.archunit.lang.ArchRule;

/** Architecture rules enforcing layered structure (D-02) and banking abstraction (D-03). */
@AnalyzeClasses(packages = "com.prosperity")
class ArchitectureTest {

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
}
