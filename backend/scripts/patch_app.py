#!/usr/bin/env python3
"""Append agent FC code to app.js"""
with open("D:/projects/web-demo/app.js", "a", encoding="utf-8") as f:
    f.write(open("patch_app_js.txt", "r", encoding="utf-8").read())
print("Done")
