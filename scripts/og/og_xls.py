#!/usr/bin/env python3
"""시행규칙 별표 1~14(분장사무) 엑셀(.xlsb/.xls/.xlsx) → {시트:[[제목,[사무…]]…]}"""
import re, os

def sheets(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == '.xlsb':
        from pyxlsb import open_workbook
        with open_workbook(path) as wb:
            for name in wb.sheets:
                with wb.get_sheet(name) as sh:
                    yield name, [tuple(c.v for c in r) for r in sh.rows()]
    elif ext == '.xls':
        import xlrd
        wb = xlrd.open_workbook(path)
        for ws in wb.sheets():
            yield ws.name, [tuple(None if (c == '' or c is None) else c for c in ws.row_values(i)) for i in range(ws.nrows)]
    else:
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        for ws in wb:
            yield ws.title, [tuple(r) for r in ws.iter_rows(values_only=True)]

def parse(path):
    out = {}
    for title, rows in sheets(path):
        cur = None; lst = []
        for r in rows:
            a = r[0] if len(r) > 0 else None; b = r[1] if len(r) > 1 else None
            if a and str(a).strip() and (b is None or str(b).strip() == ''):
                t = str(a).strip()
                if t in ('구   분', '구 분') or re.match(r'^\[별표|^\(별표|분장사무명', t) and not t.endswith('제3조 관련)'):
                    continue
                cur = t; lst.append([t, []])
            elif b is not None and str(b).strip() and cur is not None:
                d = (str(r[2]) if len(r) > 2 and r[2] else '').replace('\xa0', ' ').strip()
                if d: lst[-1][1].append(d)
        out[title] = lst
    return out
