"""Insert the UI index-build chapter and renumber existing chapters safely."""
from __future__ import annotations
import hashlib
import re

REVISION='revisions/ui_index_build_20261025'
BEFORE_SHA256='67b5fa3b0d6c6bcc253bd50779d81d18a97b0ad5747040baefe6c24e56d30af3'
ANCHOR='<a id="index-build"></a>'
TOC_ROW='| [2. UI에서 색인을 만드는 주체와 과정](#index-build) | |'


def renumber(text,delta):
    low,high=(2,6) if delta==1 else (3,7)
    digits=f'[{low}-{high}]'
    output=[]
    inside=False
    for line in text.splitlines():
        if line.startswith('```'):
            inside=not inside
        if not inside:
            line=re.sub(r'^(#{2,3} )('+digits+r')(?=[. ])',lambda m:m[1]+str(int(m[2])+delta),line)
            line=re.sub(r'(?<![\d.])('+digits+r')(\.\d+)?절',lambda m:str(int(m[1])+delta)+(m[2] or '')+'절',line)
            line=re.sub(r'(\[)('+digits+r')(?=\. )',lambda m:m[1]+str(int(m[2])+delta),line)
        output.append(line)
    return '\n'.join(output)+'\n'


def insert(source,section):
    assert hashlib.sha256(source.encode()).hexdigest()==BEFORE_SHA256,'Reconcile changed report before adding chapter'
    text=renumber(source,1)
    toc='| [1. 일곱 방식의 원리와 실제 색인 예시](#methods) | [부록 A. 상세 성적과 통계](#detail) |'
    assert text.count(toc)==1
    text=text.replace(toc,toc+'\n'+TOC_ROW,1)
    marker='<a id="design"></a>'
    assert text.count(marker)==1
    return text.replace(marker,ANCHOR+'\n\n'+section.strip()+'\n\n'+marker,1)


def previous_document(current,section):
    block=ANCHOR+'\n\n'+section.strip()+'\n\n'
    assert current.count(block)==1 and current.count(TOC_ROW)==1
    restored=current.replace(block,'',1).replace(TOC_ROW+'\n','',1)
    return renumber(restored,-1)
