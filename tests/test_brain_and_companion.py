from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sonic.db import Base, MemoryNote
from sonic.brain import run_tool
from scripts.windows_agent import execute_allowed, system_status


def test_memory_is_only_saved_when_requested():
    engine=create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        denied=run_tool(db,"memory_save",{"fact":"I enjoy astronomy"},"Tell me about astronomy")
        assert denied["error"]=="MEMORY_REQUIRES_EXPLICIT_USER_REQUEST"
        approved=run_tool(db,"memory_save",{"fact":"I enjoy astronomy"},"Ingat saya suka astronomi")
        assert approved["saved"] is True
        found=run_tool(db,"memory_search",{"query":"astronomy"},"Find memory")
        assert len(found["results"]) == 1
        rejected=run_tool(db,"memory_save",{"fact":"my password abcdef"},"Ingat password saya")
        assert rejected["error"]=="SENSITIVE_OR_INVALID_MEMORY_REJECTED"


def test_no_free_form_pc_command():
    assert execute_allowed("system.status")["capabilities"]==["system.status"]
    for command in ("shell.exec","files.delete","sketchup.run","mt5.order","powershell"):
        try:
            execute_allowed(command)
        except ValueError:
            continue
        raise AssertionError(command+" unexpectedly allowed")
