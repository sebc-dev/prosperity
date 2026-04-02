package com.prosperity.auth;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.when;

import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.security.core.userdetails.UsernameNotFoundException;

/** Unit tests for CustomUserDetailsService with mocked UserRepository. */
@ExtendWith(MockitoExtension.class)
class CustomUserDetailsServiceTest {

  @Mock private UserRepository userRepository;
  @InjectMocks private CustomUserDetailsService customUserDetailsService;

  @Test
  void loads_user_by_email_returns_user_details() {
    var user = new User("admin@test.com", "{bcrypt}hashedpassword", "Admin");
    user.setRole(Role.ADMIN);
    when(userRepository.findByEmail("admin@test.com")).thenReturn(Optional.of(user));

    var result = customUserDetailsService.loadUserByUsername("admin@test.com");

    assertThat(result.getUsername()).isEqualTo("admin@test.com");
    assertThat(result.getPassword()).isEqualTo("{bcrypt}hashedpassword");
    assertThat(result.getAuthorities()).extracting("authority").containsExactly("ROLE_ADMIN");
  }

  @Test
  void loads_user_by_email_throws_when_not_found() {
    when(userRepository.findByEmail("unknown@test.com")).thenReturn(Optional.empty());

    assertThatThrownBy(() -> customUserDetailsService.loadUserByUsername("unknown@test.com"))
        .isInstanceOf(UsernameNotFoundException.class);
  }
}
