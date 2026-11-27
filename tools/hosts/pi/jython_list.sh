# shellcheck shell=bash
# The reader of jython_scripts.txt, the list of the jython the Mac and the Pi install. Bash 3.2 and up: the Mac
# sources it from tools/hosts/deploy/common.sh, the Pi apply step from the deploy drop (cats/scripts/pi/).

# jython_list LIST: print each "ROLE PATH" line of LIST, in file order, without its comments and blank lines.
# Returns 1, naming the file and line on stderr, when LIST is missing or empty, or a line is not a known ROLE
# (startup, pi, sibling, part) and one relative .py PATH with no "." or ".." segment, or a PATH is listed twice.
jython_list() {
  local list="$1" line role path extra n=0 rows=""
  if [[ ! -f "$list" ]]; then
    echo "jython list missing: $list" >&2
    return 1
  fi
  while IFS= read -r line || [[ -n "$line" ]]; do
    n=$((n + 1))
    [[ -z "${line//[[:space:]]/}" || "$line" == \#* ]] && continue
    read -r role path extra <<<"$line"
    case "$role" in
      startup|pi|sibling|part) ;;
      *) echo "$list:$n: unknown role '$role' (startup, pi, sibling or part)" >&2; return 1 ;;
    esac
    if [[ -z "$path" || -n "$extra" || "$path" == /* || "$path" != *.py || "/$path/" == */../* || "/$path/" == */./* ]]; then
      echo "$list:$n: expected '$role PATH', one relative .py path with no '.' or '..' segment: $line" >&2
      return 1
    fi
    if [[ $'\n'"$rows" == *" $path"$'\n'* ]]; then
      echo "$list:$n: $path is listed twice" >&2
      return 1
    fi
    rows+="$role $path"$'\n'
  done <"$list"
  if [[ -z "$rows" ]]; then
    echo "jython list names no script: $list" >&2
    return 1
  fi
  printf '%s' "$rows"
}
