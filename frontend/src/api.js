const API_BASE = import.meta.env.VITE_API_BASE || '/api';

export async function fetchState() {
  const res = await fetch(`${API_BASE}/state`);
  if (!res.ok) throw new Error(res.statusText);
  return res.json();
}

export async function moveKnight(to_location_name, knight_name = null) {
  const res = await fetch(`${API_BASE}/move_knight`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ to_location_name, knight_name }),
  });
  if (!res.ok) throw new Error(res.statusText);
  return res.json();
}

export async function addKnight(location_name, name = 'Knight') {
  const res = await fetch(`${API_BASE}/add_knight?location_name=${encodeURIComponent(location_name)}&name=${encodeURIComponent(name)}`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error(res.statusText);
  return res.json();
}

export async function deleteKnight(id) {
  const res = await fetch(`${API_BASE}/delete_knight`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id }),
  });
  if (!res.ok) throw new Error(res.statusText);
  return res.json();
}

export async function createTarget(location_name = null, linked_dragon_spot_id = null) {
  const res = await fetch(`${API_BASE}/create_target`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ location_name, linked_dragon_spot_id }),
  });
  if (!res.ok) throw new Error(res.statusText);
  return res.json();
}

export async function deleteTarget(id) {
  const res = await fetch(`${API_BASE}/delete_target`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id }),
  });
  if (!res.ok) throw new Error(res.statusText);
  return res.json();
}

export async function deleteDragonSpot(id) {
  const res = await fetch(`${API_BASE}/delete_dragon_spot`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id }),
  });
  if (!res.ok) throw new Error(res.statusText);
  return res.json();
}

export async function resetSession() {
  const res = await fetch(`${API_BASE}/reset`, { method: 'POST' });
  if (!res.ok) throw new Error(res.statusText);
  return res.json();
}

/** @param {Blob} audioBlob */
export async function transcribeAudio(audioBlob) {
  const form = new FormData();
  form.append('file', audioBlob, 'recording.webm');
  const res = await fetch(`${API_BASE}/transcribe`, {
    method: 'POST',
    body: form,
  });
  if (!res.ok) throw new Error(await res.text());
  const data = await res.json();
  return data.text ?? '';
}

export async function chat(userText) {
  const res = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_text: userText }),
  });
  if (!res.ok) throw new Error(res.statusText);
  return res.json();
}
