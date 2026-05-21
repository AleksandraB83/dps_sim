import sys
import os

# Make 'import server' work when pytest is run from any directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
