'use client';
import { useEffect, useState } from 'react';

// 인증(5차) 전까지 localStorage 닉네임을 클라이언트 식별자로 사용
export function useMe() {
  const [me, setMe] = useState('');
  useEffect(() => {
    let v = localStorage.getItem('gf_me');
    if (!v) { v = '게스트-' + Math.random().toString(36).slice(2, 6); localStorage.setItem('gf_me', v); }
    setMe(v);
  }, []);
  const update = (name) => {
    const v = (name || '').trim();
    if (!v) return;
    localStorage.setItem('gf_me', v);
    setMe(v);
  };
  return [me, update];
}
