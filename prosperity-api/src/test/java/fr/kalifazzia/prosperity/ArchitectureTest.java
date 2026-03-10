package fr.kalifazzia.prosperity;

import com.tngtech.archunit.core.importer.ImportOption;
import com.tngtech.archunit.junit.AnalyzeClasses;
import com.tngtech.archunit.junit.ArchTest;
import com.tngtech.archunit.lang.ArchRule;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;
import static com.tngtech.archunit.library.dependencies.SlicesRuleDefinition.slices;

@AnalyzeClasses(packages = "fr.kalifazzia.prosperity", importOptions = ImportOption.DoNotIncludeTests.class)
class ArchitectureTest {

    @ArchTest
    static final ArchRule features_should_not_depend_on_each_other =
            slices().matching("fr.kalifazzia.prosperity.(*)..")
                    .ignoreDependency(
                            clazz -> clazz.getPackageName().startsWith("fr.kalifazzia.prosperity.shared"),
                            clazz -> true)
                    .should().notDependOnEachOther()
                    .because("Features must be isolated (vertical slice). Use shared kernel for cross-cutting concerns.");

    @ArchTest
    static final ArchRule controllers_should_not_access_repositories_directly =
            noClasses().that().haveSimpleNameEndingWith("Controller")
                    .should().dependOnClassesThat().haveSimpleNameEndingWith("Repository")
                    .because("Controllers must go through services, not access repositories directly.");

    @ArchTest
    static final ArchRule shared_should_not_depend_on_features =
            noClasses().that().resideInAPackage("..shared..")
                    .should().dependOnClassesThat().resideInAnyPackage(
                            "..account..", "..auth..", "..user..", "..category..")
                    .because("Shared kernel must not depend on feature packages.");
}
