#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
Create a Clarity user through the authenticated administrator API.

Usage:
  scripts/create_user.sh \
    --url https://reports.example.com \
    --username jane.smith \
    --full-name "Dr Jane Smith" \
    [--registration-number PSY0000000001] \
    [--role clinician] \
    [--admin-username admin]

Roles are "clinician" (default) or "admin". Both passwords are prompted for
without echo and are never accepted as command-line arguments.
EOF
}

fail() {
  printf 'Error: %s\n' "$1" >&2
  exit 1
}

require_value() {
  [[ $# -ge 2 && -n "$2" ]] || fail "Option $1 requires a value."
}

json_quote() {
  jq -Rs .
}

url=""
username=""
full_name=""
registration_number=""
role="clinician"
admin_username="admin"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --url)
      require_value "$@"
      url="$2"
      shift 2
      ;;
    --username)
      require_value "$@"
      username="$2"
      shift 2
      ;;
    --full-name)
      require_value "$@"
      full_name="$2"
      shift 2
      ;;
    --registration-number)
      require_value "$@"
      registration_number="$2"
      shift 2
      ;;
    --role)
      require_value "$@"
      role="$2"
      shift 2
      ;;
    --admin-username)
      require_value "$@"
      admin_username="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "Unknown option: $1. Run with --help for usage."
      ;;
  esac
done

[[ -n "$url" ]] || fail "--url is required."
[[ -n "$username" ]] || fail "--username is required."
[[ -n "$full_name" ]] || fail "--full-name is required."
[[ "$url" == https://* ]] || fail "--url must use HTTPS."
[[ "$role" == "clinician" || "$role" == "admin" ]] || fail "--role must be clinician or admin."

for dependency in curl jq mktemp; do
  command -v "$dependency" >/dev/null 2>&1 || fail "$dependency is required but is not installed."
done

while [[ "$url" == */ ]]; do
  url="${url%/}"
done

umask 077
cookie_file="$(mktemp)"
admin_password=""
new_password=""
new_password_confirm=""
csrf_token=""

cleanup() {
  rm -f -- "$cookie_file"
  unset admin_password admin_password_json login_payload
  unset new_password new_password_confirm new_password_json create_payload
  unset csrf_token
}
trap cleanup EXIT
trap 'exit 130' HUP INT TERM

read -r -s -p "Administrator password for ${admin_username}: " admin_password
printf '\n'

admin_username_json="$(printf '%s' "$admin_username" | json_quote)"
admin_password_json="$(printf '%s' "$admin_password" | json_quote)"
login_payload="{\"username\":${admin_username_json},\"password\":${admin_password_json}}"

login_response=""
if ! login_response="$({
  printf '%s' "$login_payload" |
    curl --silent --show-error --fail-with-body \
      --connect-timeout 10 \
      --max-time 30 \
      --cookie-jar "$cookie_file" \
      --header 'Content-Type: application/json' \
      --data-binary @- \
      "$url/api/auth/login"
})"; then
  login_error="$(printf '%s' "$login_response" | jq -r '.error // "request_failed"' 2>/dev/null || true)"
  fail "Administrator login failed (${login_error:-request_failed})."
fi

unset admin_password admin_password_json login_payload
csrf_token="$(printf '%s' "$login_response" | jq -r '.csrf_token // empty')"
unset login_response
[[ -n "$csrf_token" ]] || fail "Login response did not contain a CSRF token."

read -r -s -p "Password for new user ${username}: " new_password
printf '\n'
read -r -s -p 'Confirm new user password: ' new_password_confirm
printf '\n'

[[ "$new_password" == "$new_password_confirm" ]] || fail "New user passwords do not match."
[[ ${#new_password} -ge 14 ]] || fail "Password must contain at least 14 characters."
[[ "$new_password" =~ [A-Z] ]] || fail "Password must contain an upper-case character."
[[ "$new_password" =~ [a-z] ]] || fail "Password must contain a lower-case character."
[[ "$new_password" =~ [0-9] ]] || fail "Password must contain a numeric character."
unset new_password_confirm

username_json="$(printf '%s' "$username" | json_quote)"
full_name_json="$(printf '%s' "$full_name" | json_quote)"
registration_number_json="$(printf '%s' "$registration_number" | json_quote)"
role_json="$(printf '%s' "$role" | json_quote)"
new_password_json="$(printf '%s' "$new_password" | json_quote)"
create_payload="{\"username\":${username_json},\"full_name\":${full_name_json},\"registration_number\":${registration_number_json},\"role\":${role_json},\"password\":${new_password_json}}"

create_response=""
if ! create_response="$({
  printf '%s' "$create_payload" |
    curl --silent --show-error --fail-with-body \
      --connect-timeout 10 \
      --max-time 30 \
      --cookie "$cookie_file" \
      --header 'Content-Type: application/json' \
      --header "X-CSRF-Token: $csrf_token" \
      --data-binary @- \
      "$url/api/auth/users"
})"; then
  create_error="$(printf '%s' "$create_response" | jq -r '.message // .error // "request_failed"' 2>/dev/null || true)"
  fail "User creation failed (${create_error:-request_failed})."
fi

unset new_password new_password_json create_payload
printf 'Created %s user %s (%s).\n' \
  "$role" \
  "$(printf '%s' "$create_response" | jq -r '.username')" \
  "$(printf '%s' "$create_response" | jq -r '.id')"

if ! curl --silent --show-error --fail \
  --connect-timeout 10 \
  --max-time 30 \
  --request POST \
  --cookie "$cookie_file" \
  --header "X-CSRF-Token: $csrf_token" \
  "$url/api/auth/logout" >/dev/null; then
  printf 'Warning: the temporary administrator session could not be logged out; its cookie was discarded.\n' >&2
fi

printf 'Deliver the password to the user through an approved secure channel.\n'
