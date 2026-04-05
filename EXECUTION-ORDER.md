# Phase 2 — Execution Order

## Wave 1 (aucune dependance)

```
/gsd:execute-phase 2 --plan 01
```
Backend deps + Flyway session tables + application.yml

```
/gsd:execute-phase 2 --plan 05
```
Frontend AuthService + guards + interceptor + proxy

## Wave 2 (depend de wave 1)

```
/gsd:execute-phase 2 --plan 02
```
DTOs + CustomUserDetailsService + SecurityConfig

```
/gsd:execute-phase 2 --plan 06
```
Setup wizard + Login page (PrimeNG)

## Wave 3 (depend de wave 2)

```
/gsd:execute-phase 2 --plan 03
```
AuthService + AuthController (5 endpoints)

```
/gsd:execute-phase 2 --plan 07
```
Layout shell + dashboard + routing avec guards

## Wave 4 (depend de wave 3)

```
/gsd:execute-phase 2 --plan 04
```
Tests integration + unit (TDD)

---

Penser a `/clear` entre chaque plan pour un contexte frais.
