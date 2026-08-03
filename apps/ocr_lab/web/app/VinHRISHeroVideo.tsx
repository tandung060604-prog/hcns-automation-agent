"use client";

import { useRef, useState } from "react";

const HERO_LOOP_SECONDS = 26;

export default function VinHRISHeroVideo() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const [soundEnabled, setSoundEnabled] = useState(false);

  const keepVideoLoop = () => {
    const video = videoRef.current;
    const audio = audioRef.current;
    if (video && video.currentTime >= HERO_LOOP_SECONDS) {
      video.currentTime = 0;
      if (audio && soundEnabled) audio.currentTime = 0;
    }
  };

  const keepAudioLoop = () => {
    const audio = audioRef.current;
    const video = videoRef.current;
    if (audio && audio.currentTime >= HERO_LOOP_SECONDS) {
      audio.currentTime = 0;
      if (video) video.currentTime = 0;
    }
  };

  const toggleSound = async () => {
    const audio = audioRef.current;
    const video = videoRef.current;
    if (!audio) return;

    if (soundEnabled) {
      audio.pause();
      setSoundEnabled(false);
      return;
    }

    audio.currentTime = video ? video.currentTime % HERO_LOOP_SECONDS : 0;
    audio.volume = 0.22;
    try {
      await audio.play();
      setSoundEnabled(true);
    } catch {
      setSoundEnabled(false);
    }
  };

  return (
    <div className="vinhris-hero-video" aria-label="Video nền hành trình văn phòng và con người">
      <video
        ref={videoRef}
        className="vinhris-hero-video-media"
        autoPlay
        loop
        muted
        playsInline
        preload="metadata"
        poster="/assets/template-first-local-workflow.png"
        onTimeUpdate={keepVideoLoop}
        aria-hidden="true"
      >
        <source src="/assets/vinhris-hero-source.mp4" type="video/mp4" />
      </video>
      <audio ref={audioRef} preload="metadata" loop onTimeUpdate={keepAudioLoop}>
        <source src="/assets/vinhris-hero-music.mp3" type="audio/mpeg" />
      </audio>
      <button
        className="vinhris-hero-audio-toggle"
        type="button"
        onClick={toggleSound}
        aria-pressed={soundEnabled}
        aria-label={soundEnabled ? "Tắt nhạc nền" : "Bật nhạc nền"}
      >
        <span className="vinhris-audio-dot" aria-hidden="true" />
        {soundEnabled ? "Tắt âm thanh" : "Bật âm thanh"}
      </button>
    </div>
  );
}
