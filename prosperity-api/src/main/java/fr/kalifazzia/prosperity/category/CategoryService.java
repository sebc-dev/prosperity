package fr.kalifazzia.prosperity.category;

import com.fasterxml.uuid.Generators;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

@Service
public class CategoryService {

    private final CategoryRepository categoryRepository;

    public CategoryService(CategoryRepository categoryRepository) {
        this.categoryRepository = categoryRepository;
    }

    @Transactional(readOnly = true)
    public List<Category> getCategories(UUID userId) {
        List<Category> result = new ArrayList<>();
        result.addAll(categoryRepository.findByIsDefaultTrue());
        result.addAll(categoryRepository.findByCreatedBy(userId));
        return result;
    }

    @Transactional
    public Category createCategory(String nameKey, String icon, UUID userId) {
        Category category = new Category(
                Generators.timeBasedEpochGenerator().generate(),
                nameKey,
                icon,
                false,
                userId
        );
        return categoryRepository.save(category);
    }
}
