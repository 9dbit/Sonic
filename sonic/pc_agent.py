"""Owner PC actions for local or cloud chat, using existing verified broker.

The model never writes executable paths, installer arguments or approvals.
Inspection is bounded read-only. Install consumes the exact authenticated
inspection and still creates an explicit same-chat approval proposal.
"""
from __future__ import annotations
import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from . import auth, software
from .db import OperatorRequest, get_db
from .chat_actions import ChatAction
from .engine import execute_chat

router=APIRouter()

class Inspect(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    package_id:str=Field(min_length=2,max_length=128)
    version:str=Field(min_length=1,max_length=80)
    accept_source_agreements:bool=False
    accept_package_agreements:bool=False
    request_id:str=Field(min_length=1,max_length=128,pattern=r'^[A-Za-z0-9_-]+$')

class InstallReview(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    inspection_id:str=Field(min_length=36,max_length=36)
    request_id:str=Field(min_length=1,max_length=128,pattern=r'^[A-Za-z0-9_-]+$')

@router.post('/api/pc-agent/inspect')
async def inspect(body:Inspect,owner:dict=Depends(auth.require_owner_write),db:Session=Depends(get_db)):
    try:
        args=software.clean_request('software.inspect',body.model_dump(exclude={'request_id'}))
    except ValueError as e:
        raise HTTPException(422,str(e)) from None
    return await execute_chat(db,'Periksa software '+args['package_id']+' versi '+args['version'],
        None,owner,request_id=body.request_id,
        resolved_action=ChatAction('automatic','software.inspect',args))

@router.post('/api/pc-agent/install-review')
async def install_review(body:InstallReview,owner:dict=Depends(auth.require_owner_write),db:Session=Depends(get_db)):
    inspection=db.get(OperatorRequest,body.inspection_id)
    if (not inspection or inspection.owner_sid!=auth.sha256(owner['sid'])
        or inspection.action!='software.inspect' or inspection.state!='done'):
        raise HTTPException(404,'Pemeriksaan software tidak ditemukan pada sesi ini.')
    result=json.loads(inspection.result_json or '{}')
    try:
        payload=software.clean_request('software.install',{
            'plan':result.get('plan'),'plan_sha256':result.get('plan_sha256')})
    except ValueError:
        raise HTTPException(409,'Periksa ulang paket dengan persetujuan sumber/lisensi yang sesuai sebelum instalasi.') from None
    software.require_inspection(db,auth.sha256(owner['sid']),inspection.device_id,payload)
    plan=payload['plan']
    return await execute_chat(db,'Tinjau instalasi '+plan['package_id']+' versi '+plan['version'],
        None,owner,request_id=body.request_id,
        resolved_action=ChatAction('review','software.install',payload))
