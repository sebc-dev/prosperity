package com.prosperity.auth;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;

/**
 * Main Spring Security configuration.
 *
 * <p>Configures CSRF with SPA mode for Angular XSRF-TOKEN compatibility, permits public auth
 * endpoints, requires authentication for all others, and provides PasswordEncoder and
 * AuthenticationManager beans.
 */
@Configuration
@EnableWebSecurity
public class SecurityConfig {

  /** Configures the security filter chain with CSRF SPA mode and endpoint authorization. */
  @Bean
  public SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http.csrf(csrf -> csrf.spa().ignoringRequestMatchers("/api/auth/login", "/api/auth/setup"))
        .authorizeHttpRequests(
            auth ->
                auth.requestMatchers("/api/auth/login", "/api/auth/setup", "/api/auth/status")
                    .permitAll()
                    .requestMatchers(HttpMethod.GET, "/api/auth/me")
                    .permitAll()
                    .requestMatchers("/actuator/health")
                    .permitAll()
                    .anyRequest()
                    .authenticated())
        .logout(
            logout ->
                logout
                    .logoutUrl("/api/auth/logout")
                    .logoutSuccessHandler((req, res, auth) -> res.setStatus(200))
                    .invalidateHttpSession(true)
                    .deleteCookies("SESSION"))
        .sessionManagement(session -> session.maximumSessions(1))
        .exceptionHandling(
            ex ->
                ex.authenticationEntryPoint(
                    (req, res, authEx) -> res.sendError(HttpServletResponse.SC_UNAUTHORIZED)));
    return http.build();
  }

  /** Delegating password encoder with bcrypt as default (supports future algorithm migration). */
  @Bean
  public PasswordEncoder passwordEncoder() {
    return PasswordEncoderFactories.createDelegatingPasswordEncoder();
  }

  /** Authentication manager using DaoAuthenticationProvider backed by UserDetailsService. */
  @Bean
  public AuthenticationManager authenticationManager(
      UserDetailsService userDetailsService, PasswordEncoder passwordEncoder) {
    var provider = new DaoAuthenticationProvider(userDetailsService);
    provider.setPasswordEncoder(passwordEncoder);
    return new ProviderManager(provider);
  }
}
