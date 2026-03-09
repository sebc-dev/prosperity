package fr.kalifazzia.prosperity.account;

import com.fasterxml.uuid.Generators;
import fr.kalifazzia.prosperity.account.dto.AccountDto;
import fr.kalifazzia.prosperity.account.dto.CreateAccountRequest;
import fr.kalifazzia.prosperity.shared.exception.ResourceNotFoundException;
import fr.kalifazzia.prosperity.user.User;
import fr.kalifazzia.prosperity.user.UserRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;

@Service
public class AccountService {

    private final AccountRepository accountRepository;
    private final PermissionRepository permissionRepository;
    private final UserRepository userRepository;

    public AccountService(AccountRepository accountRepository,
                          PermissionRepository permissionRepository,
                          UserRepository userRepository) {
        this.accountRepository = accountRepository;
        this.permissionRepository = permissionRepository;
        this.userRepository = userRepository;
    }

    @Transactional
    public AccountDto createAccount(CreateAccountRequest request, UUID currentUserId) {
        UUID accountId = Generators.timeBasedEpochGenerator().generate();

        Account account = new Account(
                accountId,
                request.name(),
                request.bankName(),
                request.accountType(),
                currentUserId,
                request.currency(),
                request.initialBalance(),
                request.color()
        );
        accountRepository.save(account);

        // Grant MANAGE permission to owner
        AccountPermission ownerPermission = new AccountPermission(
                Generators.timeBasedEpochGenerator().generate(),
                accountId,
                currentUserId,
                PermissionLevel.MANAGE
        );
        permissionRepository.save(ownerPermission);

        // If SHARED, grant WRITE to the designated user
        if (request.accountType() == AccountType.SHARED) {
            if (request.sharedWithUserId() == null) {
                throw new IllegalArgumentException("sharedWithUserId is required for SHARED accounts");
            }
            if (request.sharedWithUserId().equals(currentUserId)) {
                throw new IllegalArgumentException("Cannot share an account with yourself");
            }
            User sharedUser = userRepository.findById(request.sharedWithUserId())
                    .orElseThrow(() -> new ResourceNotFoundException("Shared user not found"));
            AccountPermission otherPermission = new AccountPermission(
                    Generators.timeBasedEpochGenerator().generate(),
                    accountId,
                    sharedUser.getId(),
                    PermissionLevel.WRITE
            );
            permissionRepository.save(otherPermission);
        }

        return toDto(account, PermissionLevel.MANAGE);
    }

    @Transactional(readOnly = true)
    public List<AccountDto> getAccountsForUser(UUID userId) {
        List<Account> accounts = accountRepository.findAllByUserId(userId);

        Map<UUID, AccountPermission> permissionsByAccountId = permissionRepository
                .findAllByUserId(userId)
                .stream()
                .collect(Collectors.toMap(AccountPermission::getAccountId, Function.identity()));

        return accounts.stream()
                .map(account -> {
                    AccountPermission permission = permissionsByAccountId.get(account.getId());
                    PermissionLevel level = permission != null
                            ? permission.getPermissionLevel()
                            : PermissionLevel.READ;
                    return toDto(account, level);
                })
                .collect(Collectors.toList());
    }

    private AccountDto toDto(Account account, PermissionLevel permissionLevel) {
        return new AccountDto(
                account.getId(),
                account.getName(),
                account.getBankName(),
                account.getAccountType(),
                account.getCurrency(),
                account.getInitialBalance(),
                account.getCurrentBalance(),
                account.getColor(),
                permissionLevel
        );
    }
}
