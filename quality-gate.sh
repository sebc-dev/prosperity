#!/usr/bin/env bash
set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'
BOLD='\033[1m'

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/prosperity-api"
FRONTEND_DIR="$ROOT_DIR/prosperity-web"

# State
FAIL_FAST=true
RUN_BACKEND=true
RUN_FRONTEND=true
MODE="standard"
RESULTS=()
HAS_FAILURE=false

usage() {
    echo -e "${BOLD}Usage:${NC} $0 [quick|standard|full] [options]"
    echo ""
    echo "Modes:"
    echo "  quick      Compilation + lint only (~15s)"
    echo "  standard   Tests + lint + build (~2min) [default]"
    echo "  full       Everything + SpotBugs + PIT + security scans (~10min)"
    echo ""
    echo "Options:"
    echo "  --backend-only     Skip frontend checks"
    echo "  --frontend-only    Skip backend checks"
    echo "  --no-fail-fast     Run all checks even if some fail"
    echo "  -h, --help         Show this help"
}

log_step() {
    echo -e "\n${BLUE}━━━ ${BOLD}$1${NC}${BLUE} ━━━${NC}"
}

log_pass() {
    RESULTS+=("${GREEN}✓${NC} $1")
    echo -e "  ${GREEN}✓${NC} $1"
}

log_fail() {
    RESULTS+=("${RED}✗${NC} $1")
    HAS_FAILURE=true
    echo -e "  ${RED}✗${NC} $1"
    if $FAIL_FAST; then
        print_summary
        exit 1
    fi
}

log_skip() {
    RESULTS+=("${YELLOW}○${NC} $1 (skipped)")
    echo -e "  ${YELLOW}○${NC} $1 (skipped)"
}

run_check() {
    local name="$1"
    shift
    if "$@" > /dev/null 2>&1; then
        log_pass "$name"
    else
        log_fail "$name"
    fi
}

print_summary() {
    echo -e "\n${BOLD}━━━ Summary ━━━${NC}"
    for r in "${RESULTS[@]}"; do
        echo -e "  $r"
    done
    echo ""
    if $HAS_FAILURE; then
        echo -e "  ${RED}${BOLD}QUALITY GATE FAILED${NC}"
    else
        echo -e "  ${GREEN}${BOLD}QUALITY GATE PASSED${NC}"
    fi
    echo ""
}

# Parse args
for arg in "$@"; do
    case $arg in
        quick|standard|full) MODE="$arg" ;;
        --backend-only) RUN_FRONTEND=false ;;
        --frontend-only) RUN_BACKEND=false ;;
        --no-fail-fast) FAIL_FAST=false ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $arg"; usage; exit 1 ;;
    esac
done

echo -e "${BOLD}Quality Gate${NC} — mode: ${YELLOW}${MODE}${NC}"
echo -e "Backend: $(if $RUN_BACKEND; then echo 'yes'; else echo 'skip'; fi) | Frontend: $(if $RUN_FRONTEND; then echo 'yes'; else echo 'skip'; fi)"

# ──────────────────────────────────
# BACKEND
# ──────────────────────────────────
if $RUN_BACKEND; then
    log_step "Backend"

    if [ ! -f "$BACKEND_DIR/pom.xml" ]; then
        log_fail "Backend: pom.xml not found"
    else
        # Detect Maven command
        if command -v mvn &> /dev/null; then
            MVN="mvn"
        elif [ -f "$BACKEND_DIR/mvnw" ]; then
            MVN="$BACKEND_DIR/mvnw"
        else
            log_skip "Backend: Maven not found (install mvn or add mvnw)"
            MVN=""
        fi

        if [ -n "$MVN" ]; then
            case $MODE in
                quick)
                    run_check "Backend: compile" $MVN -f "$BACKEND_DIR/pom.xml" compile -q
                    ;;
                standard)
                    run_check "Backend: verify (compile + tests)" $MVN -f "$BACKEND_DIR/pom.xml" verify -q
                    ;;
                full)
                    run_check "Backend: verify (compile + tests)" $MVN -f "$BACKEND_DIR/pom.xml" verify -q
                    run_check "Backend: SpotBugs" $MVN -f "$BACKEND_DIR/pom.xml" spotbugs:check -q
                    if $MVN -f "$BACKEND_DIR/pom.xml" help:describe -Dplugin=org.pitest:pitest-maven -q > /dev/null 2>&1; then
                        run_check "Backend: PIT mutation testing" $MVN -f "$BACKEND_DIR/pom.xml" org.pitest:pitest-maven:mutationCoverage -q
                    else
                        log_skip "Backend: PIT mutation testing (plugin not configured)"
                    fi
                    ;;
            esac
        fi
    fi
fi

# ──────────────────────────────────
# FRONTEND
# ──────────────────────────────────
if $RUN_FRONTEND; then
    log_step "Frontend"

    if [ ! -f "$FRONTEND_DIR/package.json" ]; then
        log_fail "Frontend: package.json not found"
    else
        # Ensure i18n stubs are generated
        if [ -f "$FRONTEND_DIR/scripts/generate-i18n-stubs.js" ]; then
            (cd "$FRONTEND_DIR" && npx paraglide-js compile --project ./project.inlang --outdir ./src/lib/i18n --silent 2>/dev/null && node scripts/generate-i18n-stubs.js 2>/dev/null) || true
        fi

        case $MODE in
            quick)
                run_check "Frontend: type check" bash -c "cd '$FRONTEND_DIR' && npm run check"
                run_check "Frontend: lint" bash -c "cd '$FRONTEND_DIR' && npm run lint"
                ;;
            standard)
                run_check "Frontend: type check" bash -c "cd '$FRONTEND_DIR' && npm run check"
                run_check "Frontend: lint" bash -c "cd '$FRONTEND_DIR' && npm run lint"
                run_check "Frontend: tests" bash -c "cd '$FRONTEND_DIR' && npm run test"
                run_check "Frontend: build" bash -c "cd '$FRONTEND_DIR' && npm run build"
                ;;
            full)
                run_check "Frontend: type check" bash -c "cd '$FRONTEND_DIR' && npm run check"
                run_check "Frontend: lint" bash -c "cd '$FRONTEND_DIR' && npm run lint"
                run_check "Frontend: tests" bash -c "cd '$FRONTEND_DIR' && npm run test"
                run_check "Frontend: build" bash -c "cd '$FRONTEND_DIR' && npm run build"
                run_check "Frontend: npm audit" bash -c "cd '$FRONTEND_DIR' && npm audit --audit-level=high"
                if command -v trivy &> /dev/null; then
                    run_check "Frontend: Trivy scan" trivy fs "$FRONTEND_DIR" --severity HIGH,CRITICAL --exit-code 1 --quiet
                else
                    log_skip "Frontend: Trivy (not installed)"
                fi
                ;;
        esac
    fi
fi

# ──────────────────────────────────
# SECURITY (full mode only)
# ──────────────────────────────────
if [ "$MODE" = "full" ]; then
    log_step "Security"

    if command -v snyk &> /dev/null; then
        if $RUN_BACKEND; then
            run_check "Security: Snyk backend" snyk test --file="$BACKEND_DIR/pom.xml" --severity-threshold=high
        fi
        if $RUN_FRONTEND; then
            run_check "Security: Snyk frontend" snyk test --file="$FRONTEND_DIR/package.json" --severity-threshold=high
        fi
    else
        log_skip "Security: Snyk (not installed — npm install -g snyk)"
    fi

    if command -v trivy &> /dev/null; then
        run_check "Security: Trivy filesystem" trivy fs "$ROOT_DIR" --severity HIGH,CRITICAL --exit-code 1 --quiet
    else
        log_skip "Security: Trivy (not installed — see https://trivy.dev)"
    fi
fi

print_summary

if $HAS_FAILURE; then
    exit 1
fi
