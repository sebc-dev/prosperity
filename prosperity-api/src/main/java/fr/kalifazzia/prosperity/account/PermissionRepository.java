package fr.kalifazzia.prosperity.account;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

@Repository
public interface PermissionRepository extends JpaRepository<AccountPermission, UUID> {

    Optional<AccountPermission> findByAccountIdAndUserId(UUID accountId, UUID userId);

    List<AccountPermission> findAllByAccountId(UUID accountId);
}
