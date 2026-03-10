package fr.kalifazzia.prosperity;

import com.tngtech.archunit.base.DescribedPredicate;
import com.tngtech.archunit.core.domain.JavaClass;
import com.tngtech.archunit.core.importer.ImportOption;
import com.tngtech.archunit.junit.AnalyzeClasses;
import com.tngtech.archunit.junit.ArchTest;
import com.tngtech.archunit.lang.ArchRule;

import static com.tngtech.archunit.core.domain.JavaClass.Predicates.resideInAPackage;
import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;
import static com.tngtech.archunit.library.dependencies.SlicesRuleDefinition.slices;

@AnalyzeClasses(packages = "fr.kalifazzia.prosperity", importOptions = ImportOption.DoNotIncludeTests.class)
class ArchitectureTest {

    @ArchTest
    static final ArchRule features_should_not_depend_on_each_other =
            slices().matching("fr.kalifazzia.prosperity.(*)..")
                    .should().notDependOnEachOther()
                    // shared is cross-cutting, allowed everywhere
                    .ignoreDependency(resideInAPackage("..shared.."), DescribedPredicate.<JavaClass>alwaysTrue())
                    .ignoreDependency(DescribedPredicate.<JavaClass>alwaysTrue(), resideInAPackage("..shared.."))
                    // user is a core domain, account and auth may reference User entity
                    .ignoreDependency(DescribedPredicate.<JavaClass>alwaysTrue(), resideInAPackage("..user.."))
                    .because("Features must be isolated (vertical slice). Allowed dependencies: shared (cross-cutting) and user (core domain).");

    @ArchTest
    static final ArchRule controllers_should_not_access_repositories_directly =
            noClasses().that().haveSimpleNameEndingWith("Controller")
                    .should().dependOnClassesThat().haveSimpleNameEndingWith("Repository")
                    .because("Controllers must go through services, not access repositories directly.");

    @ArchTest
    static final ArchRule shared_should_not_depend_on_features =
            noClasses().that().resideInAPackage("..shared..")
                    .should().dependOnClassesThat().resideInAnyPackage(
                            "..account..", "..category..")
                    .because("Shared kernel must not depend on feature packages (except user and auth for security wiring).");
}
