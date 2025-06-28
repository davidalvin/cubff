#!/bin/bash
ulimit -v 5242880
echo "Memory limit set to 5GB"
exec "$@"
