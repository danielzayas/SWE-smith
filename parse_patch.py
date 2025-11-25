#!/usr/bin/env python3
"""
Parse PR patch and separate into solution patch and test patch.
"""
import sys
from unidiff import PatchSet

def parse_patch(patch_file):
    """Parse patch and separate into solution and test patches."""
    with open(patch_file, 'r') as f:
        patch_content = f.read()
    
    patch_set = PatchSet(patch_content)
    patch_fix = ""
    patch_test = ""
    
    for file_diff in patch_set:
        # Check if file path contains test-related keywords
        if any(test_word in file_diff.path.lower() for test_word in ["test", "tests", "e2e", "testing"]):
            patch_test += str(file_diff)
        else:
            patch_fix += str(file_diff)
    
    return patch_fix, patch_test

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python parse_patch.py <patch_file>")
        sys.exit(1)
    
    patch_file = sys.argv[1]
    patch_fix, patch_test = parse_patch(patch_file)
    
    print("=== SOLUTION PATCH ===")
    print(patch_fix)
    print("\n=== TEST PATCH ===")
    print(patch_test)
    
    # Save to files for verification
    with open("patch_fix.diff", "w") as f:
        f.write(patch_fix)
    with open("patch_test.diff", "w") as f:
        f.write(patch_test)
    
    print("\nSaved patch_fix.diff and patch_test.diff")
