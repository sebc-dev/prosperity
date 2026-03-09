package fr.kalifazzia.prosperity.account;

import fr.kalifazzia.prosperity.account.dto.AccountDto;
import fr.kalifazzia.prosperity.account.dto.CreateAccountRequest;
import fr.kalifazzia.prosperity.auth.JwtService;
import fr.kalifazzia.prosperity.shared.security.SecurityUtils;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api/accounts")
public class AccountController {

    private final AccountService accountService;
    private final JwtService jwtService;

    public AccountController(AccountService accountService, JwtService jwtService) {
        this.accountService = accountService;
        this.jwtService = jwtService;
    }

    @PostMapping
    public ResponseEntity<AccountDto> createAccount(
            @Valid @RequestBody CreateAccountRequest request,
            HttpServletRequest httpRequest) {
        UUID currentUserId = SecurityUtils.extractUserId(httpRequest, jwtService);
        AccountDto account = accountService.createAccount(request, currentUserId);
        return ResponseEntity.status(HttpStatus.CREATED).body(account);
    }

    @GetMapping
    public ResponseEntity<List<AccountDto>> getAccounts(HttpServletRequest httpRequest) {
        UUID currentUserId = SecurityUtils.extractUserId(httpRequest, jwtService);
        List<AccountDto> accounts = accountService.getAccountsForUser(currentUserId);
        return ResponseEntity.ok(accounts);
    }
}
