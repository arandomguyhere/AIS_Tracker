#!/usr/bin/env python3
"""
AIS_Tracker Test Runner

Run all tests: python run_tests.py
Run specific: python run_tests.py test_database
Run verbose:  python run_tests.py -v
"""

import os
import sys
import unittest
import argparse
from datetime import datetime


def run_tests(verbosity=2, pattern='test*.py', specific_module=None):
    """Run the test suite."""
    print("=" * 60)
    print("AIS_Tracker Test Suite")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print()

    # Ensure we're in the right directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    # Add to path
    sys.path.insert(0, script_dir)

    # Discover and run tests
    loader = unittest.TestLoader()

    if specific_module:
        # Run specific test module
        try:
            suite = loader.loadTestsFromName(f'tests.{specific_module}')
        except ModuleNotFoundError:
            print(f"Error: Test module 'tests.{specific_module}' not found")
            return False
    else:
        # Discover all tests
        suite = loader.discover('tests', pattern=pattern)

    # Run tests
    runner = unittest.TextTestRunner(verbosity=verbosity)
    result = runner.run(suite)

    # Summary
    print()
    print("=" * 60)
    print("Test Summary")
    print("=" * 60)
    print(f"  Tests run:  {result.testsRun}")
    print(f"  Failures:   {len(result.failures)}")
    print(f"  Errors:     {len(result.errors)}")
    print(f"  Skipped:    {len(result.skipped)}")
    print()

    if result.wasSuccessful():
        print("  STATUS: ALL TESTS PASSED")
    else:
        print("  STATUS: SOME TESTS FAILED")

        if result.failures:
            print()
            print("  Failed tests:")
            for test, _ in result.failures:
                print(f"    - {test}")

        if result.errors:
            print()
            print("  Errors:")
            for test, _ in result.errors:
                print(f"    - {test}")

    print("=" * 60)

    return result.wasSuccessful()


def main():
    parser = argparse.ArgumentParser(description='Run AIS_Tracker tests')
    parser.add_argument(
        'module',
        nargs='?',
        help='Specific test module to run (e.g., test_database)'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Verbose output'
    )
    parser.add_argument(
        '-q', '--quiet',
        action='store_true',
        help='Quiet output'
    )

    args = parser.parse_args()

    verbosity = 2
    if args.verbose:
        verbosity = 3
    elif args.quiet:
        verbosity = 1

    success = run_tests(
        verbosity=verbosity,
        specific_module=args.module
    )

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
