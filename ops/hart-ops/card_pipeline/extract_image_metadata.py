#!/usr/bin/env python3
"""Dump car-card image metadata to CSV.

Delegates to ``process_car_images.py``, which crops every photo in
``Images/``, OCRs stencilled markings, matches the roster, and writes
``image_metadata.csv`` plus ``CarImages/*.png``.
"""

from process_car_images import main

if __name__ == "__main__":
    main()
