#!/bin/bash

pyinstaller --collect-all PyQt5 \
	--windowed \
	--onefile bping.py
