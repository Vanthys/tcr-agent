---
theme: default
class: relative overflow-hidden
transition: fade
title: BIO/AI Hackathon
info: |
  ## BIO/AI Hackathon - Demonstrating TCR-Agent
  
  - 03-08-2026
  - created by Olvier Hahn and Marcel Skumantz
---
<div class="absolute inset-0 -z-20">
  <img 
    src="https://media4.giphy.com/media/v1.Y2lkPTZjMDliOTUyc2hnZXQwNGFzcnU4a3J6MmQ5YWpzZ2V3Mjl1a2tmbTN3OXNobWltbiZlcD12MV9naWZzX3NlYXJjaCZjdD1n/AWavg3wftQic0/source.gif"
    class="w-full h-full object-cover blur-md scale-110"
  /> 
</div>
<div class="absolute inset-0 -z-10 bg-gradient-to-br from-white/90 via-white/80 to-white/90"></div>

<div class="grid grid-cols-[2fr_1fr] gap-8 items-center h-full">

  <div>
    <h1><span class="bg-gradient-to-r from-green-400 to-blue-500 bg-clip-text text-transparent view-transition-title"> BIO/AI Hackathon</span></h1>
    <h2><span class="opacity-60">From orphan TCRs to experiment-ready hypothesis</span></h2>
    <br/>
    Oliver Hahn, PhD and Marcel Skumantz
  </div>

  <div class="flex justify-center">
    <img src="../images/01_pic.svg" class="max-h-90 w-full object-contain"/>
  </div>

</div>
---
transition: view-transition
layout: full
---

<div class="absolute inset-0 -z-20">
  <img 
    src="https://media4.giphy.com/media/v1.Y2lkPTZjMDliOTUyc2hnZXQwNGFzcnU4a3J6MmQ5YWpzZ2V3Mjl1a2tmbTN3OXNobWltbiZlcD12MV9naWZzX3NlYXJjaCZjdD1n/AWavg3wftQic0/source.gif"
    class="w-full h-full object-cover blur-md scale-110"
  /> 
</div>
<div class="absolute inset-0 -z-10 bg-gradient-to-br from-white/90 via-white/80 to-white/90"></div>

<div class="h-full flex items-center justify-center">

  <div class="max-w-6xl w-full grid grid-cols-[1fr_1fr] gap-10 items-center">
    <!-- Left: image -->
    <div class="flex justify-center items-center">
      <img
        src="../images/02_picNoText.svg"
        class="max-h-120 object-contain"
      />
    </div>
    <!-- Right: animated blocks -->
        <div class="flex flex-col justify-center">
      <div class="grid grid-cols-1 gap-6 text-left max-w-md mx-auto">
      <div
        v-motion
        :initial="{ opacity: 0, y: 16 }"
        :enter="{ opacity: 1, y: 0, transition: { duration: 500, delay: 200 } }"
        class="bg-white/5 backdrop-blur-md rounded-xl p-6"
      >
        <h3 class="text-blue-400 text-sm uppercase tracking-wider">Read</h3>
        <p class="mt-2 text-lg">
          Ability to find/sequence T-Cell Receptors from nature
        </p>
      </div>
      <div
        v-motion
        :initial="{ opacity: 0, y: 16 }"
        :enter="{ opacity: 1, y: 0, transition: { duration: 500, delay: 350 } }"
        class="bg-white/5 backdrop-blur-md rounded-xl p-6"
      >
        <h3 class="text-red-400 text-sm uppercase tracking-wider">Write</h3>
        <p class="mt-2 text-lg">
          Generate synthetic TCRs <em>(TCRAFT 2026)</em>
        </p>
      </div>
      <div
        v-motion
        :initial="{ opacity: 0, y: 16 }"
        :enter="{ opacity: 1, y: 0, transition: { duration: 500, delay: 500 } }"
        class="bg-white/5 backdrop-blur-md rounded-xl p-6"
      >
        <h3 class="text-purple-400 text-sm uppercase tracking-wider">Reason ?</h3>       
      </div>
    </div>
    </div>
  </div>

</div>
---
transition: view-transition
layout: full
---

<div class="absolute inset-0 -z-10 bg-gradient-to-br from-white/100 via-white/90 to-white/100"></div>

<div class="absolute inset-0 overflow-hidden">
  <iframe
    class="absolute top-0 left-0 border-0"
    title="Inline Frame Example"
    src="http://localhost:5173/"
    style="width:125%; height:125%; transform:scale(0.8); transform-origin: top left;"
  ></iframe>
</div>


---
transition: view-transition
layout: full
---

<div class="absolute inset-0 -z-10 bg-gradient-to-br from-white/100 via-white/90 to-white/100"></div>

<div class="absolute inset-0 overflow-hidden">
   <img 
    src="../images/03_pic.svg"
    class="w-full h-full object-contain"
  /> 

</div>


