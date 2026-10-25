"""Read-only navigation plans. Every node ID is resolved against the real graph.

Plans are applied by the authenticated browser; prepared does not mean applied.
"""
from __future__ import annotations
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session
from .memory import normalize


class QueryArgs(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    query: str = Field(min_length=1, max_length=150)


class NodeArgs(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    node_id: str = Field(min_length=1, max_length=120)


class NeighborArgs(NodeArgs):
    depth: int = Field(default=1, ge=1, le=3)


class EmptyArgs(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


def tool(name, description, properties, required):
    return {'type': 'function', 'name': name, 'description': description, 'strict': True,
            'parameters': {'type': 'object', 'properties': properties, 'required': required, 'additionalProperties': False}}


GRAPH_TOOLS = [
    tool('graph_search', 'Find real graph nodes. Prepares highlighting; does not write data. Use only to answer a request to show/find knowledge.',
         {'query': {'type': 'string'}}, ['query']),
    tool('graph_focus', 'Prepare a focus/inspector action for an exact existing graph node ID. Never invent an ID.',
         {'node_id': {'type': 'string'}}, ['node_id']),
    tool('graph_neighbors', 'Prepare the existing connections of an exact node ID at depth 1-3. No new relation is created.',
         {'node_id': {'type': 'string'}, 'depth': {'type': 'integer', 'minimum': 1, 'maximum': 3}}, ['node_id', 'depth']),
    tool('graph_reset', 'Prepare resetting the graph view to all nodes. Does not delete memories.', {}, []),
]
ARG_TYPES = {'graph_search': QueryArgs, 'graph_focus': NodeArgs, 'graph_neighbors': NeighborArgs, 'graph_reset': EmptyArgs}


def run_graph_tool(db: Session, name: str, arguments: dict) -> dict:
    if name not in ARG_TYPES:
        return {'error': 'TOOL_NOT_ALLOWED'}
    try:
        args = ARG_TYPES[name].model_validate(arguments)
    except ValidationError:
        return {'error': 'INVALID_TOOL_ARGUMENTS'}
    if name == 'graph_reset':
        action = {'type': 'graph.reset'}
        result = {'prepared': True}
    else:
        # Import lazily: knowledge reads the actual brain registry.
        from .knowledge import graph_snapshot
        snapshot = graph_snapshot(db)
        lookup = {n['id']: n for n in snapshot['nodes']}
        if name == 'graph_search':
            query = normalize(args.query).casefold()
            if not query:
                return {'error': 'QUERY_REQUIRED'}
            matches = [n for n in snapshot['nodes'] if query in (n['label'] + ' ' + n['detail']).casefold()]
            matches.sort(key=lambda n: (n['category'] != 'memory', query != n['label'].casefold(), -n['degree']))
            nodes = [{'id': n['id'], 'label': n['label'], 'category': n['category'], 'source': n['source']} for n in matches[:12]]
            action = {'type': 'graph.search', 'query': args.query.strip(), 'node_ids': [n['id'] for n in nodes]}
            result = {'prepared': True, 'results': nodes, 'total_matches': len(matches), 'graph_truncated': snapshot['truncated']}
        else:
            node = lookup.get(args.node_id)
            if node is None:
                return {'error': 'GRAPH_NODE_NOT_FOUND'}
            action = {'type': 'graph.focus' if name == 'graph_focus' else 'graph.neighbors', 'node_id': node['id']}
            result = {'prepared': True, 'node': {'id': node['id'], 'label': node['label'], 'detail': node['detail'], 'source': node['source']}}
            if name == 'graph_neighbors':
                action['depth'] = args.depth
                seen, frontier = {node['id']}, {node['id']}
                for _ in range(args.depth):
                    nxt = set()
                    for edge in snapshot['edges']:
                        if edge['source'] in frontier: nxt.add(edge['target'])
                        if edge['target'] in frontier: nxt.add(edge['source'])
                    frontier = nxt - seen
                    seen.update(frontier)
                result['connected_node_ids'] = sorted(seen - {node['id']})[:100]
                result['connection_count'] = len(seen) - 1
                result['notice'] = 'Existing structural, lexical or owner-confirmed links, not inferred semantic facts.'
    db.info.setdefault('ui_actions', []).append(action)
    result['ui_action'] = action
    result['notice_ui'] = 'A navigation plan, not proof that the browser applied it.'
    return result


def direct_graph_command(text: str, selected_node_id: str | None = None) -> tuple[str, dict] | None:
    """Anchored navigation shortcuts; ordinary questions remain model conversations."""
    text = normalize(text).strip()
    text = re.sub(r'^(?:sonic[,:.!\s]+)?(?:(?:tolong|please)\s+)?', '', text, flags=re.I).rstrip('.!')
    if re.fullmatch(r'(?:kembali ke (?:seluruh|semua) (?:brain|graph)|reset (?:brain|graph)(?: view)?|show (?:the )?(?:whole|entire) (?:brain|graph))', text, re.I):
        return 'graph_reset', {}
    match = re.fullmatch(r'(?:buka|open|fokus(?:kan)?(?: pada)?|focus(?: on)?)\s+(?:memory|memori|catatan|note)\s*#?\s*(\d+)', text, re.I)
    if match:
        return 'graph_focus', {'node_id': 'memory:' + str(int(match.group(1)))}
    match = re.fullmatch(r'^(?:lihat|tampilkan|buka|fokus(?:kan)?|show|open|focus)\s+(?:(?:detail|informasi|integrasi|koneksi)\s+){0,3}node\s+(.{2,120})$', text, re.I)
    if match:
        return 'graph_search', {'query': match.group(1).strip(' "“”')}
    match = re.fullmatch(r'(?:tampilkan|cari|show|find)\s+(?:memory|memori|catatan|node|topik|notes?|memories|knowledge)\s+(?:tentang|mengenai|about|for)\s+(.{1,150})', text, re.I)
    if match:
        return 'graph_search', {'query': match.group(1).strip()}
    match = re.fullmatch(r'(?:tampilkan|perlihatkan|show)\s+(?:hubungannya|koneksinya|connections|its connections)(?:\s+(?:depth|kedalaman)\s+([123]))?', text, re.I)
    if match:
        return 'graph_neighbors', {'node_id': selected_node_id or '', 'depth': int(match.group(1) or 1)}
    return None


def direct_graph_reply(result: dict, name: str) -> str:
    if result.get('error'):
        return 'Pilih node yang tersedia terlebih dahulu. Tidak ada perubahan pada memory atau graph.'
    if name == 'graph_search':
        count = result['total_matches']
        return (f'Ditemukan {count} node yang cocok. Hasil tersedia pada Search di Neural Brain.' if count else
                'Tidak ada node yang cocok dalam graph saat ini. Tidak ada memory baru yang dibuat.')
    if name == 'graph_reset':
        return 'Tampilan seluruh Neural Brain siap dibuka. Memory tidak dihapus.'
    if name == 'graph_neighbors':
        return f"Koneksi untuk {result['node']['label']} siap ditampilkan. Ini hubungan yang sudah ada, bukan relasi baru."
    return f"Catatan siap dibuka di Inspector: {result['node']['label']}"
