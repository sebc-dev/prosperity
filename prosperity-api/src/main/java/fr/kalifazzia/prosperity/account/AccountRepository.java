package fr.kalifazzia.prosperity.account;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.UUID;

@Repository
public interface AccountRepository extends JpaRepository<Account, UUID> {

    @Query("SELECT a FROM Account a JOIN AccountPermission p ON a.id = p.accountId WHERE p.userId = :userId")
    List<Account> findAllByUserId(@Param("userId") UUID userId);
}
