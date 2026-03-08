---
theme: default
class: relative overflow-hidden text-black
transition: fade
title: BIO/AI Hackathon
info: |
  ## BIO/AI Hackathon - Demonstrating TCR-Agent
  
  - 03-08-2026
  - created by Olvier Hahn and Marcel Skumantz
---

<div class="absolute inset-0 -z-20">
  <!-- <img 
  src="https://media4.giphy.com/media/v1.Y2lkPTZjMDliOTUyc2hnZXQwNGFzcnU4a3J6MmQ5YWpzZ2V3Mjl1a2tmbTN3OXNobWltbiZlcD12MV9naWZzX3NlYXJjaCZjdD1n/AWavg3wftQic0/source.gif"
  class="w-full h-full object-cover blur-md scale-110"
  /> -->
</div>
<div class="absolute inset-0 -z-10 bg-gradient-to-br from-white/100 via-white/90 to-white/100"></div>

# <span class="bg-gradient-to-r from-green-400 to-blue-500 bg-clip-text text-transparent view-transition-title"> BIO/AI Hackathon </span>

### <span class="opacity-60"> Demonstrating **TCR-Agent** </span>


Oliver Hahn, PhD and Marcel Skumantz
<!--
Welcome to my presentation, I will mention 3 ideas, 
its important to note that I have already worked a bit on all of them I guess
-->

---
transition: view-transition
---

<div class="absolute inset-0 -z-20">
  <img 
    src="https://i.makeagif.com/media/7-04-2020/zpBEQV.gif"
    class="w-full h-full object-cover blur-sm scale-110"
  />
</div>
<div class="absolute inset--1 -z-10 bg-gradient-to-br from-black/95 via-black/80 to-black/95"></div>

<div class="h-full flex items-center justify-center text-center">
  <div
  >
    <h1
      v-motion
      data-morph="challenge-title"
      class="text-6xl font-bold"
    >
      <span class="bg-gradient-to-r from-red-400 to-blue-500 bg-clip-text text-transparent view-transition-title">
        Talking about Something 
      </span>
    </h1>
    <p class="mt-6 text-2xl opacity-80">
      Interactive expert control - without breaking scale or reproducibility.
    </p>
  </div>
</div>

--- 
transition: view-transition
---

<!-- Slide 2: Title up + cards in -->
<div class="absolute inset-0 -z-20">
  <img 
    src="https://media1.giphy.com/media/v1.Y2lkPTc5MGI3NjExdzN5ODNkZTlmM3g0Z3FpNTBraGp6ejN1MWRuM2E2ZncxcnNheXF3cyZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/ryefzyqqx1xZO5GgEu/giphy.gif"
    class="w-full h-full object-cover blur-sm scale-110"
  />
</div>
<div class="absolute inset--1 -z-10 bg-gradient-to-br from-black/95 via-black/80 to-black/95"></div>

<div class="max-w-6xl mx-auto h-full flex flex-col">

  <div class="pt-8">
    <h1
      v-motion
      data-morph="challenge-title"
      class="text-4xl font-bold"
    >
      <span class="bg-gradient-to-r from-blue-400 to-red-500 bg-clip-text text-transparent view-transition-title">
        Human-in-the-Loop Molecular Docking & Dynamics
      </span>
    </h1>
  </div>

  <div class="mt-10 grid grid-cols-2 gap-8 text-left">
    <div v-motion
      :initial="{ opacity: 0, y: 16 }"
      :enter="{ opacity: 1,  y: 0, transition: { duration: 500, delay: 200 } }" 
      class="bg-white/5 backdrop-blur-md rounded-xl p-6">
      <h3 class="text-blue-400 text-sm uppercase tracking-wider">Who</h3>
       <ul class="mt-2 text-lg">
        <li> Computational chemists </li>
        <li> Early discovery </li>
      </ul>
    </div>
    <div v-motion
      :initial="{ opacity: 0, y: 16 }"
      :enter="{ opacity: 1,  y: 0, transition: { duration: 500, delay: 350 } }" 
      class="bg-white/5 backdrop-blur-md rounded-xl p-6">
      <h3 class="text-red-400 text-sm uppercase tracking-wider">What</h3>
      <p class="mt-2 text-lg">Interactive docking + MD</p>
    </div>
       <div v-motion
      :initial="{ opacity: 0, y: 16 }"
      :enter="{ opacity: 1,  y: 0, transition: { duration: 500, delay: 500 } }" 
      class="bg-white/5 backdrop-blur-md rounded-xl p-6">
      <h3 class="text-blue-400 text-sm uppercase tracking-wider">Where</h3>
      <ul class="mt-2 text-lg">
        <li> Academia </li>
        <li> small/mid biotech </li>
      </ul>
    </div>
      <div v-motion
      :initial="{ opacity: 0, y: 16 }"
      :enter="{ opacity: 1,  y: 0, transition: { duration: 500, delay: 650 } }" 
      class="bg-white/5 backdrop-blur-md rounded-xl p-6">
      <h3 class="text-red-400 text-sm uppercase tracking-wider">Why</h3>
      <ul class="mt-2 text-lg">
        <li> Fragmented tools </li>
        <li> slow loops </li>
      </ul>
    </div>
  </div>
</div>


---
transition: view-transition
---


<!-- Slide 2: Title up + cards in -->
<div class="absolute inset-0 -z-20">
</div>
<div class="absolute inset--1 -z-10 bg-gradient-to-br from-white/100 via-white/90 to-white/100"></div>


<iframe
  id="inlineFrameExample"
  title="Inline Frame Example"
  width="800"
  height="400"
  src="http://localhost:5173/">
</iframe>
