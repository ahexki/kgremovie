# KG ReMovie version 3.0

> Recap dubbing tool: English, Chinese, Japanese, Korean, Thai … (20 languages + auto-detect) → Myanmar · release **KG ReMovie 3.0** (`VERSION.txt`)

## 🆕 Version 3.0

| **Multi-language → Myanmar** — ဘာသာစကား ၂၀ + **Auto-detect**
| **Slow motion ပိုနှေးနိုင်ပြီ** — **0.25×** နဲ့ **0.35×** ထပ်ထည့်
| **ကျား/မ အသံခွဲခြင်း** — မူလစကားပြောသူရဲ့ pitch အရ Thiha (ကျား) / Nilar (မ)
| **မူလအသံ + dub အသံ ရောစပ်ခြင်း** — မူလအသံ 0–100%၊ dub ပြောနေချိန် အလိုအလျောက် လျှော့

### Multi-language → Myanmar
**Source language** dropdown ထဲက ဘာသာစကားတစ်ခု ရွေးပါ: English, Chinese, Japanese, Korean, Thai, Vietnamese, Indonesian, Malay, Filipino, Hindi, Bengali, Urdu, Arabic, Turkish, Russian, Spanish, French, German, Portuguese, Italian — သို့မဟုတ် **Auto-detect** (Whisper က ဗီဒီယိုတစ်ခုချင်းစီရဲ့ ဘာသာကို ရှာပြီး AI ကို ပြောပြတယ်)။
- Whisper က multilingual `small` (~480 MB) ကို သုံးတယ် (English က `small.en`)။ ပိုတိကျချင်ရင် `config.json` မှာ `"whisper_model_other": "medium"` (Chinese အတွက် `whisper_model_zh`)။
- နာမည်တွေကို မူရင်းအသံထွက်အတိုင်း မြန်မာအက္ခရာနဲ့ တစ်မျိုးတည်း ရေးတယ်၊ idiom တွေကို အဓိပ္ပာယ်နဲ့ ပြောတယ်။
  
- **အရည်အသွေးက ဘာသာစကားပေါ် မူတည်တယ်** — English / Spanish / French / German လို ဘာသာတွေက Whisper မှာ ပိုကောင်းပြီး အရင်းအမြစ်နည်းတဲ့ ဘာသာတွေက ပိုမှားနိုင်တယ်။ **Check transcript first** နဲ့ အရင်စစ်။

- ဘာသာတစ်ခုချင်းစီက သီးသန့် cache / Output Video folder ရှိတယ်။

### Slow motion — ပိုနှေးအောင်
Speed ကို **0.25× / 0.35× / 0.5× / 0.7×** ကနေ ရွေးတယ် (0.25× = ၄ ဆ နှေး)။ ကြားဖြတ် frame တွေကို ရောစပ်ထားလို့ လှုပ်ခါမှု မရှိပါဘူး။ Auto edit ရဲ့ slow ထဲမှာလည်း 0.35× ပါတယ်။

### ကျား/မ အသံခွဲခြင်း (Voice mode)
| Mode |
| Selected voice | ရွေးထားတဲ့ Edge voice တစ်ခုတည်း (မူလအတိုင်း) |
| Male voice (Thiha) | စာကြောင်းအားလုံး ကျားအသံ |
| Female voice (Nilar) | စာကြောင်းအားလုံး မအသံ |
| **Auto — by speaker** | မူလအသံကို နားထောင်ပြီး စာကြောင်းတစ်ကြောင်းချင်း ကျား/မ ရွေး |

Auto က မူလအသံရဲ့ **pitch (F0)** ကို တိုင်းတယ်: ~155 Hz အောက် = ကျား၊ ~180 Hz အထက် = မ၊ ကြားထဲက ဆိုရင် အနီးဆုံး စကားပြောသူအမျိုးအစားကို ယူတယ်၊ စကားမကြားရတဲ့ အပိုင်းက အနီးဆုံး စာကြောင်းကို လိုက်တယ်။
**ကန့်သတ်ချက်:** pitch ကပဲ ကြည့်တာမို့ အသံနိမ့်တဲ့ အမျိုးသမီး၊ အသံမြင့်တဲ့ အမျိုးသား၊ ကလေး၊ သီချင်း/ဂီတ ပြင်းတာတွေမှာ မှားနိုင်တယ်၊ ကျား နှစ်ယောက်ကို ခွဲလို့ မရဘူး (အသံတူတူ ဖြစ်မယ်)။ Meta MMS ရွေးထားရင် MMS က အသံတစ်မျိုးတည်းမို့ ကျား/မ ကို Edge fallback အတွက်ပဲ သုံးတယ်။

### မူလအသံ + dub အသံ ရောစပ်ခြင်း
**Original audio** slider (0–100%): 0% = dub တစ်ခုတည်း (အရင်အတိုင်း)။ တင်လိုက်ရင် မူလဗီဒီယိုရဲ့ အသံ (ဂီတ၊ ပတ်ဝန်းကျင်၊ မူလစကား) ကို dub အောက်မှာ ထည့်ပေးတယ်။
- မူလအသံကို video အပိုင်းတစ်ခုချင်းစီရဲ့ အမြန်/အနှေးအတိုင်း ချိန်ပေးတာမို့ ရုပ်ပုံနဲ့ ကိုက်တယ် (pitch မပြောင်းဘူး)။
- **Duck the original while the dub speaks** ဖွင့်ထားရင် dub ပြောနေချိန် မူလအသံ ~၂၄ dB ကျပြီး ရပ်တာနဲ့ ပြန်တက်တယ်။
- Dub ရဲ့ volume ကို ရှိပြီးသား **Voice vol** slider နဲ့ ဆက်ချိန်လို့ရတယ်။
- မူလစကားကို အသံထဲ ထပ်ထည့်ရင် dub နဲ့ ရောပြီး ကြားနိုင်တယ် — မူလစကားမလိုရင် အနိမ့် (20–30%) ထား၊ ဂီတ/ပတ်ဝန်းကျင်ပဲ လိုချင်ရင် Duck ဖွင့်ပါ။

## Version 2.0

| Feature |
|---|---|
| **AI refine pass** — ဘာသာပြန်ပြီးသား မြန်မာစာကို AI က ထပ်ပြီး သဘာဝကျအောင် ပြန်ပြင်တယ် | Settings → *AI refine pass* |
| **Video Look** — ဗီဒီယိုတစ်ပုဒ်လုံးကို colour filter + strength % | Production Tools → *Video Look & Auto Edit* |
| **Vignette %** — ထောင့်တွေကို မှောင်စေတယ် (0–100%) | အတူတူ |
| **Slow motion** — ၅ / ၁၀ စက္ကန့် slow ဖြစ်တဲ့ အပိုင်းတွေ | အတူတူ |
| **Auto edit** — flip + zoom + freeze + vignette + slow ကို random ရောနှောပြီး အလိုအလျောက် edit | အတူတူ |
| **Check transcript first** — ပထမ ၆၀ စက္ကန့်ကိုပဲ Whisper နဲ့ ဖတ်ပြီး စာကို ကြိုကြည့်တယ် (AI/key မလိုဘူး၊)


### AI refine pass
Settings ထဲက **AI refine pass (polish the Burmese)** ကို tick လုပ်ပါ။ ပထမအကြိမ် ဘာသာပြန်ပြီးရင် AI ကို ဒုတိယအကြိမ် ခေါ်ပြီး စာကြောင်းတစ်ကြောင်းချင်းစီကို
မူရင်း (source) နဲ့ နှိုင်းယှဉ်ကာ ပိုသဘာဝကျတဲ့ ပြောစကားအဖြစ် ပြန်ပြင်ပါတယ်။
- အဓိပ္ပာယ်၊ နာမည်၊ ဂဏန်း၊ အချိန်ကိုက်မှု မပြောင်းပါဘူး (စာကြောင်း ID တစ်ခုချင်းစီ အတွင်းမှာပဲ ပြင်တယ်၊ အရှည် ၈၀%–၁၂၅% ခန့်)။
- စစ်ဆေးမှု (အရှည်၊ English စာလုံး၊ မှတ်ချက်) မကျတဲ့ စာကြောင်းကို ပထမအကြိမ် စာအတိုင်း ပြန်ထားပါတယ် — ပိုဆိုးမသွားပါဘူး။
- AI key ကုန်သွားရင် job မပျက်ပါဘူး၊ refine ကိုပဲ ကျော်ပြီး ဆက်လုပ်တယ်။ နောက်တစ်ခါ START နှိပ်ရင် ကျန်တာကို ဆက်ပြင်တယ် (`refine_checkpoint.json`)။
- Tick ဖြုတ်/ပြန်တင်လည်း ဘာသာပြန်ထားတာကို ပြန်မပြန်ပါဘူး (AI call အပိုကုန်တာပဲ ရှိတယ်)။

### Myanmar Subtitle
**Production Tools → Myanmar Subtitle → Burn in Myanmar subtitle** ကို tick လုပ်ပါ။ မြန်မာ narration စာကို ဗီဒီယိုအောက်ခြေအလယ်မှာ အသံနဲ့ ကိုက်အောင် ပြပါတယ်
(အသံစပြောတဲ့အချိန် ပေါ်၊ ပြီးရင် ပျောက်)။ စာရှည်ရင် `။ ၊` နဲ့ စာလုံးကြားမှာ ဖြတ်ပြီး subtitle အတိုလေးတွေ ခွဲပြီး အချိန်ကို အရှည်အလိုက် မျှဝေပါတယ်။ တစ်ခါမှာ ၂ ကြောင်းထက် မပိုပါဘူး။

**Size** (ဆွေ့ညီတဲ့ အရွယ်၊ 1080 canvas မှာ):

| Size | pixel |
|---|---|
| 9 (small) | 36 px |
| 12 (medium) | 48 px |
| 14 (large) | 56 px |

9:16 (ဒေါင်လိုက်) ဗီဒီယိုမှာလည်း တူညီတဲ့ အကြည့်ရအောင် canvas ရဲ့ အတိုဘက်နဲ့ အချိုးကျ ချိန်ထားပါတယ်။

**Style** (၄ မျိုး):
1. **Yellow · black stroke** (မူလ) — အဝါရောင်စာ၊ အနက်ရောင် ဘောင်
2. **White · black stroke** — အဖြူရောင်စာ၊ အနက်ရောင် ဘောင်
3. **White on black box** — အဖြူရောင်စာ၊ ဖောက်ထွင်းမြင်ရတဲ့ အနက်ရောင်ဘောက်စ်
4. **Black on yellow box** — အနက်ရောင်စာ၊ အဝါရောင်ဘောက်စ်

### Video Look + Vignette
- **Filter:** Warm, Cool, Cinematic, Vivid, Vintage, Black & White, Matte — **Strength** slider (0–100%) နဲ့ ချိန်ပါ။
- **Vignette:** 0% = မရှိ၊ 25% ≈ ထောင့်အလင်း ၇၅%၊ 50% ≈ ၅၅%၊ 100% ≈ ၁၅% (ပြားနေတဲ့ပုံမှာ တိုင်းထားတာ)။
- Title / Logo / Blur box တွေအပေါ် မသက်ရောက်ပါဘူး (overlay မတင်ခင်မှာ ထည့်တာမို့)။

### Slow motion
**Slow** (5 s / 10 s) · **Speed** (0.5× / 0.7×) · **Every** (10 / 20 / 30 / 60 s) — ဥပမာ "၃၀ စက္ကန့်ကြာတိုင်း ၅ စက္ကန့် slow"။
Freeze rhythm လိုပဲ **ရုပ်ပုံကိုပဲ** အစားထိုးတာမို့ အသံနဲ့ video အရှည် မပြောင်းပါဘူး၊ Smart Sync ကိုက်ညီမှု မပျက်ပါဘူး။

### Auto edit (random)
ဗီဒီယိုကို ၆–၁၄ စက္ကန့် section တွေ ကျပန်းခွဲပြီး section တစ်ခုချင်းစီကို ရွေးထားတဲ့ effect (**Flip, Zoom, Freeze, Vignette, Slow**) တွေကနေ ကျပန်းရောပြီး တင်ပေးပါတယ်။
- **Intensity:** Low (section ၃၅% ကို edit၊ effect ၁ ခုထိ) · Medium (၅၅%၊ ၂ ခုထိ) · High (၈၀%၊ ၃ ခုထိ)။
- **Seed:** ဂဏန်းတူရင် edit တူတူ ထွက်တယ်။ အလွတ်ထားရင် ဗီဒီယိုတစ်ခုချင်းအတွက် ပုံသေဖြစ်တယ်။
- Slow ရဲ့ အရှည်ကို *Slow* box၊ Freeze ရဲ့ အရှည်ကို *Freeze* box (Freeze rhythm ထဲက) ကနေ ယူတယ်။
- **Auto edit ဖွင့်ထားရင် Freeze rhythm နဲ့ Slow motion ကို ကျော်ပါတယ်** (Auto edit ထဲမှာ ပါပြီးသားမို့)။ Video Look ကတော့ အပေါ်ကနေ ဆက်တင်တယ်။
- အစီအစဉ်: *(Auto edit) သို့ (Freeze rhythm → Slow motion) → Video Look → Title/Logo/Blur → အသံ*။
- Render က effect တစ်ခုစီအတွက် ဗီဒီယိုကို တစ်ခါ ထပ် encode လုပ်တာမို့ အချိန်ပိုကြာတယ်။ STOP နှိပ်ရင် ပြီးသားအပိုင်းတွေ ကျန်ပြီး RESUME မှာ ဆက်လုပ်တယ်။

> English: turns an English-narrated recap/story video into the same video narrated in Myanmar
> (Burmese). The Myanmar voice leads, and the picture of every line is re-timed to it ("Smart Sync").
> See the [English section](#english) below.

---

## ဘာလုပ်ပေးလဲ

1. **နားထောင်** — English အသံကို စက်ထဲမှာပဲ Whisper (`small.en`) နဲ့ စာသားပြောင်းတယ်။ စကားလုံးတိုင်းရဲ့ အချိန်ကို ယူထားတယ်။
2. **အပိုင်းခွဲ** — စာကြောင်း၊ အပိုဒ်၊ အသံရပ်တဲ့နေရာတွေမှာ ခွဲပြီး အပိုင်းတိုင်းကို ၄.၂ စက္ကန့်လောက် (အများဆုံး ၅.၆ စက္ကန့်) ထားတယ်။ အပိုင်းများလေ ရုပ်နဲ့ အသံ ပိုကိုက်လေပါ။
3. **ဇာတ်လမ်း မှတ်ဉာဏ်** — Gemini က ဇာတ်လမ်းတစ်ခုလုံးကို အရင်ဖတ်ပြီး ဇာတ်ကောင်နာမည်၊ ဆက်နွယ်မှု၊ နေရာတွေကို မှတ်ထားတယ်။ ဒါကြောင့် နာမည်တွေ တစ်ပုဒ်လုံး တစ်မျိုးတည်း ဖြစ်တယ်။
4. **ဘာသာပြန်** — Gemini က တစ်ခါမှာ အပိုင်း ၄၀ စီ မြန်မာလို ပြန်တယ်။
   - ဇာတ်ကြောင်းပြောသူလို သဘာဝကျတဲ့ စကားပြောပုံစံနဲ့ ပြန်တယ်။
   - အကျဉ်းမချုပ်ဘူး၊ ချန်မထားဘူး။ အပိုင်းတစ်ခုရဲ့ အကြောင်းအရာကို ဘေးအပိုင်းထဲ မရွှေ့ဘူး။
   - ပြန်ပြီးတိုင်း စစ်ဆေးတဲ့အဆင့် (audit) က ချန်ခဲ့တာ၊ နေရာလွဲတာ၊ ထပ်နေတာတွေကို ပြန်ပြင်တယ်။
   - မြန်မာစာလုံးထဲ တခြားဘာသာ စာလုံး ညှပ်ဝင်လာရင် (ဥပမာ "ဧည့်ခန်း" နေရာမှာ "မင်္ဂလာခန်း") Gemini ကို ပြန်မေးတယ်။
5. **အသံထုတ်** — Edge TTS မြန်မာအသံ (Thiha ယောက်ျားသံ / Nilar မိန်းမသံ) နဲ့ ထုတ်တယ်။ "Short pauses" ဖွင့်ထားရင် Edge ထည့်တတ်တဲ့ အသံတိတ်ကို ဖြတ်လို့ စာကြောင်းကြားမှာ ~၀.၂၅ စက္ကန့်ပဲ နားတယ်။
6. **Smart Sync** — မြန်မာအသံက အချိန်ကို ဦးဆောင်ပြီး ရုပ်က လိုက်ညှိတယ်။ အသေးစိတ်ကို [Smart Sync ဘယ်လိုအလုပ်လုပ်လဲ](#smart-sync-ဘယ်လိုအလုပ်လုပ်လဲ) မှာ ကြည့်ပါ။
7. **ဖြည့်စွက်** — Blur box (မူရင်း watermark/စာတန်းဖုံးဖို့)၊ Title၊ Logo၊ Extra text၊ Zoom၊ Flip တွေကို preview ပေါ်မှာ နေရာချပြီး ထည့်လို့ရတယ်။ Video အချိုး (**16:9 / 9:16 / 1:1 / Original**) ကိုလည်း ရွေးလို့ရတယ်။

ထွက်လာတဲ့ video မှာ **မြန်မာအသံပဲ** ပါတယ်။ မူရင်း English အသံနဲ့ နောက်ခံသီချင်း မပါဘူး။

## လိုအပ်တာ

|---|---|
| Windows | 10 / 11 (64-bit) |
| Python | **3.12, 64-bit** — [python.org](https://www.python.org/downloads/) ကနေ သွင်းပါ။ "Add python.exe to PATH" နဲ့ "tcl/tk" ကို အမှန်ခြစ်ပါ |
| FFmpeg | `ffmpeg.exe` + `ffprobe.exe` — မရှိရင် `INSTALL_REQUIREMENTS.bat` က အလိုလို download လုပ်ပေးတယ် ([gyan.dev builds](https://www.gyan.dev/ffmpeg/builds/)) |
| Gemini API key | အခမဲ့ ရတယ် — [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |
| Internet | Gemini နဲ့ Edge TTS အတွက် |
| NVIDIA GPU | မဖြစ်မနေ မလိုဘူး။ ရှိရင် Whisper နဲ့ video render ပိုမြန်တယ် (NVENC)။ မရှိရင် CPU နဲ့ အလိုလို လုပ်တယ် |

## ထည့်သွင်းနည်း (တစ်ခါပဲ လုပ်)

1. ဒီ repo ကို download လုပ်ပါ (**Code → Download ZIP** ပြီးရင် ဖြည်ပါ၊ သို့မဟုတ် `git clone`)။
2. Python 3.12 ကို သွင်းပါ (အပေါ်က ဇယားကို ကြည့်ပါ)။
3. **`INSTALL_REQUIREMENTS.bat`** ကို double-click နှိပ်ပါ။ အောက်ပါတွေကို သွင်းပေးပါမယ်:
   - Python package တွေ
   - Title စာရေးဖို့ လိုတဲ့ Chromium
   - **FFmpeg** — စက်ထဲမှာ မရှိရင် (~100 MB) download လုပ်ပြီး ဒီ folder ထဲက `ffmpeg\` ထဲ ထည့်ပေးပါမယ်။ PATH ထဲ (သို့) `C:\ffmpeg\bin\` မှာ ရှိပြီးသားဆိုရင် အဲ့ဒါကိုပဲ သုံးပါတယ်။
4. **`.env.example`** ကို **`.env`** လို့ copy ကူးပါ။ ပြီးရင် ဖွင့်ပြီး key ထည့်ပါ:
   ```ini
   GEMINI_API_KEY=ကိုယ့်_key
   ```
   Key တစ်ခုထက် ပိုရှိရင် (Google project တစ်ခုစီက key) ဒီလို ထည့်လို့ရပါတယ်။ တစ်ခုရဲ့ ကန့်သတ်ချက် ပြည့်ရင် နောက်တစ်ခုကို အလိုလို ပြောင်းသုံးပါတယ်။
   ```ini
   GEMINI_IMAGE_PROJECT_1_KEY=...
   GEMINI_IMAGE_PROJECT_2_KEY=...
   ```

> ⚠️ `.env` ထဲမှာ ကိုယ့် key ရှိလို့ ဘယ်သူ့ကိုမှ မပို့ပါနဲ့၊ GitHub ပေါ်လည်း မတင်ပါနဲ့ (`.gitignore` ထဲမှာ ထည့်ထားပြီးသားပါ)။

## သုံးနည်း

**`RUN.bat`** ကို double-click နှိပ်ပါ။ Window မှာ အကွက် ၃ ကွက် ပါပါတယ်။

| နေရာ | လုပ်ရမယ့်အရာ |
|---|---|
| အပေါ် | **Source Video → Browse** နဲ့ English video ကို ရွေးပါ။ **Folder** နှိပ်ရင် folder ထဲက video တွေကို တစ်ခုပြီးတစ်ခု လုပ်ပါတယ် (ပြီးပြီးသား video တွေကို ကျော်ပါတယ်)။ **Gemini .env** မှာ `.env` ဖိုင်ကို ရွေးပါ (default က ဒီ folder ထဲက `.env`)။ |
| ဘယ်ဘက် | **Edge TTS Voice** (`my-MM-ThihaNeural` / `my-MM-NilarNeural`) နဲ့ **Edge TTS Speed** (−50% … +100%) ကို ရွေးပါ။ အောက်က **Run Logs** မှာ အလုပ်လုပ်နေတာတွေ ပြပါတယ်။ |
| ညာဘက်ဆုံး | **Preview** — slider နဲ့ `◀ 5s` / `5s ▶` နဲ့ ကြည့်ချင်တဲ့ အချိန်ကို ရွှေ့ပြီး **Refresh Frame** နှိပ်ပါ။ Title၊ Logo၊ Extra text ကို ဆွဲရွှေ့ပြီး နေရာချလို့ရပါတယ်။ Blur box ကို ဆွဲလို့ရပါတယ်။ |
| အလယ် | **Production Tools** — Zoom (1.00–1.25×)၊ Flip (ဘယ်ညာ ပြောင်းပြန်)၊ Voice vol (50–300%)၊ Short pauses၊ **Ratio** (16:9 / 9:16 / 1:1 / Original) နဲ့ **Fill** (Blur background / Black bars / Crop to fill)၊ **+ Draw Blur Box** / Delete Selected၊ Title (စာ၊ အရွယ်)၊ Logo (ဖိုင်၊ အရွယ်၊ အလင်းဖောက်မှု)၊ Extra Text Box။ |
| အောက်ခြေ | **START / RESUME** — စတယ် (ရပ်ထားတာဆိုရင် ဆက်လုပ်တယ်)။ **STOP SAFELY** — အခု လုပ်နေတဲ့ အဆင့်ပြီးမှ ရပ်ပြီး လုပ်ပြီးသမျှ သိမ်းထားတယ်။ **Output Video** — ထွက်လာတဲ့ ဖိုင်တွေ ဖွင့်ကြည့်ဖို့။ **Edit Text** — မြန်မာ narration ကို စာကြောင်းလိုက် ပြင်ဖို့ (အောက်မှာ ကြည့်ပါ)။ |

**ထွက်လာတဲ့ ဖိုင်:** `output\<video နာမည်>_<code>\edge_tts_smart_sync\final_edge_tts_smart_sync.mp4`

Output folder ထဲမှာ ကြည့်လို့ရတဲ့ ဖိုင်တွေ:
- `whisper_transcript.txt` — English စာသား
- `timestamp_translations.json` — စာပိုင်းတိုင်းရဲ့ English နဲ့ မြန်မာ
- `smart_sync_plan.json` — အချိန်ညှိထားတဲ့ plan
- `run.log` — အလုပ်လုပ်သွားတဲ့ မှတ်တမ်း

## 🆕 Chinese (中文) → Myanmar AI Dubbing

တရုတ်စကား ပြောထားတဲ့ recap / ဇာတ်လမ်းပြော video ကိုလည်း မြန်မာအသံနဲ့ dubbing လုပ်လို့ရ။

1. ဘယ်ဘက် Settings ထဲက **Source language** ကို **`Chinese 中文 → Myanmar`** လို့ ရွေးပါ။ (English video ဆိုရင် `English → Myanmar` ပဲ ထားပါ။)
2. **START / RESUME** နှိပ်ပါ။ ကျန်တာ အားလုံး English နဲ့ အတူတူပါပဲ — Whisper → Story memory → ဘာသာပြန် → audit → Edge TTS မြန်မာအသံ → Smart Sync။

Chinese mode မှာ ကွာတာတွေ:

- **Whisper** — `small.en` (English only) အစား multilingual **`small`** (~480 MB) ကို သုံးပါတယ် (ပထမအကြိမ်ပဲ download)။ ပိုတိကျချင်ရင် `config.json` ထဲ `"whisper_model_zh": "medium"` (~1.5 GB၊ ပိုနှေးတယ်) ထည့်ပါ။ Simplified Chinese ထွက်အောင် Whisper ကို လမ်းညွှန်ထားပါတယ်။
- **စာကြောင်းခွဲပုံ** — တရုတ်မှာ စကားလုံးကြားထဲ space မရှိလို့ `。！？` တို့နဲ့ `，、；：` တို့မှာ ခွဲပါတယ်။
- **ဘာသာပြန် prompt** — ဇာတ်ကောင် / နေရာ / ဂိုဏ်း နာမည်တွေကို မူရင်း တရုတ်စာလုံးနဲ့ မှတ်ထားပြီး မြန်မာစာလုံးနဲ့ **Mandarin အသံထွက်အတိုင်း** တစ်မျိုးတည်း ရေးပါတယ်။ 成语 (idiom) တွေကို စကားလုံးအလိုက် မပြန်ဘဲ အဓိပ္ပာယ်ကို သဘာဝကျကျ ပြောပါတယ်။ 师父 / 师兄 / 少爷 လို့ ခေါ်ဝေါ်ပုံတွေကိုလည်း ဆက်နွယ်မှုနဲ့ ကိုက်အောင် ရွေးပါတယ်။ မြန်မာစာထဲ တရုတ်စာလုံး ကျန်နေရင် AI ကို ပြန်မေးပါတယ်။
- **စစ်ဆေးမှု** — Whisper က တရုတ်စကား မကြားရရင် (သို့) တစ်ကြောင်းတည်း ထပ်ခါထပ်ခါ ရေးနေရင် AI ကို မခေါ်ခင် ရပ်ပြီး အကြောင်းရင်းကို ပြောပါတယ်။
- **Output folder** — Chinese job တွေက `output\<video>_<code>_zh\` လို့ သီးသန့် folder ထဲမှာ ရှိလို့ English job နဲ့ မရောပါဘူး။ Video တစ်ခုတည်းကို ဘာသာနှစ်မျိုးလုံး လုပ်လို့ရပါတယ်။

> 💡 နောက်ခံသီချင်း ပြင်းတဲ့ video၊ စကားပြောသူ အများကြီး ရောပြောတဲ့ video မှာ Whisper ရဲ့ တရုတ်စာသား မှားနိုင်ပါတယ်။ **Output Video** ထဲက `whisper_transcript.txt` ကို ဖွင့်စစ်ပြီး **Edit Text** မှာ မြန်မာစာကို ပြင်ပါ။

## 🆕 Orynx API (Gemini နဲ့ အတူ သုံးခြင်း)

[Orynx](https://orynx.dev) ရဲ့ API key ကိုလည်း Gemini key နဲ့ အတူ သုံးလို့ရပါတယ်။ `.env` ထဲမှာ ဒီလို ထည့်ပါ (နှစ်ခုလုံး ထည့်လို့ရတယ်၊ တစ်ခုတည်းလည်း ရတယ်):

```ini
GEMINI_API_KEY=ကိုယ့်_gemini_key
ORYNX_API_KEY=ကိုယ့်_orynx_key
```

- **ပုံမှန်အစီအစဉ်:** Gemini ကို အရင်သုံးပါတယ်။ Gemini key / model အားလုံး ကန့်သတ်ချက်ပြည့်သွားရင် (429, quota, 503, timeout) **Orynx ကို အလိုလို ပြောင်းသုံးပါတယ်** — တူညီတဲ့ request ကိုပဲ ပြန်ပို့လို့ ဘာမှ ပျောက်မသွားပါဘူး။ နောက်တစ်ခါ START / RESUME နှိပ်ရင် Gemini ကနေ ပြန်စပါတယ်။
- **Orynx ကို အရင်သုံးချင်ရင်:** `TRANSLATION_PROVIDER_ORDER=orynx,gemini`။ **Orynx တစ်ခုတည်း:** `TRANSLATION_PROVIDER_ORDER=orynx` (Gemini key မလိုတော့ဘူး)။
- Orynx key အများကြီးရှိရင် `ORYNX_API_KEY_2=`, `ORYNX_API_KEY_3=` ... ထည့်ပါ။ Credit ကုန်တာ၊ key သက်တမ်းကုန်တာ (401 / 402 / 403 / 429) ဆိုရင် နောက် key ကို ပြောင်းသုံးပါတယ်။
- Model: Orynx မှာ ပုံမှန် `gemini-3.8-flash` ကို သုံးပါတယ်။ ပြောင်းချင်ရင် `ORYNX_MODELS=model1,model2` (model စာရင်း: [orynx.dev/models](https://orynx.dev/models))။ Model ကို Gemini API format နဲ့ ခေါ်လို့ရတာမျိုး ဖြစ်ရပါမယ်။
- Orynx က `https://api.orynx.dev` ကို တိုက်ရိုက် ခေါ်ပါတယ် — Gemini အတွက် သုံးတဲ့ v2rayN / `GEMINI_PROXY` ကို Orynx မသုံးပါဘူး (လိုရင် `ORYNX_PROXY=` ထည့်ပါ)။
- Log ထဲမှာ `🔄 Orynx fallback (key pool exhausted) → gemini-3.8-flash` လို့ ပေါ်ရင် ပြောင်းသွားပြီလို့ သိနိုင်ပါတယ်။

## 🆕 Freeze rhythm (Production Tools → Video)

Recap videoပုံစံ — ရုပ်ပုံက 5 / 8 / 10 စက္ကန့် ပုံမှန်ပြပြီး၊ ပြီးရင် frame တစ်ခုကို 2 / 4 စက္ကန့် **freeze** လုပ်ကာ အဲဒီ frame ကို **zoom-in** ဖြစ်စေပါတယ်။ ပြီးရင် ပြန်ဆက်ပြီး ထပ်လုပ်ပါတယ်။

1. Production Tools ရဲ့ **Video** အပိုင်းမှာ **Freeze rhythm** ကို tick လုပ်ပါ။
2. **Play** (5 / 8 / 10 s)၊ **Freeze** (2 / 4 s)၊ **Zoom-in** (Off / Small ≈1.05–1.10× / Medium ≈1.10–1.20× / Large ≈1.20–1.35×) ကို ရွေးပါ။
3. START / RESUME နှိပ်ပါ။

- Freeze တစ်ခုချင်းစီမှာ zoom ပမာဏနဲ့ zoom ဝင်မယ့်နေရာ (focus) ကို **ကျပန်း** ရွေးပါတယ်။ Video တစ်ခုအတွက် ရလဒ်က ပုံသေပါ — ပြန် render လည်း အတူတူပဲ (config.json ထဲ `"freeze_rhythm": {"seed": 7}` ထည့်ရင် ပြောင်းလို့ရတယ်)။
- **ရုပ်ပုံပဲ ပြောင်းပါတယ်၊ အသံနဲ့ video အရှည် မပြောင်းပါဘူး** — Smart Sync ကိုက်ညီမှု မပျက်ပါဘူး။ Freeze ကာလမှာ ပုံမှန်ဆိုရင် ပြမယ့်ရုပ်ပုံကို freeze frame နဲ့ အစားထိုးတာပါ။
- Title / Logo / Blur box တွေက freeze အပေါ်မှာ **မလှုပ်ဘဲ** ရှိနေပါတယ် (rhythm ပြီးမှ overlay တင်တာ)။
- ဗီဒီယိုအဆုံးက ၁ စက္ကန့်အောက် အပိုင်းကို ရှေ့ပိုင်းနဲ့ ပေါင်းထည့်လို့ flicker မဖြစ်ပါဘူး။ STOP နှိပ်ရင် ပြီးသား အပိုင်းတွေ ကျန်ပြီး RESUME မှာ ဆက်လုပ်ပါတယ်။
- Render အချိန်: video တစ်ခုလုံးကို တစ်ခါ ထပ် encode လုပ်ရတာမို့ အချိန်နည်းနည်း ပိုကြာပါတယ်။

## 🆕 TTS provider — Edge TTS ကိုလည်း၊ Meta MMS ကိုလည်း ရွေးသုံးနိုင်

Settings ထဲက **TTS provider** dropdown မှာ ရွေးပါ:

| ရွေးချယ်မှု | ဘာလဲ |
|---|---|
| **Edge TTS** (မူလ) | အရင်အတိုင်းပါပဲ။ Thiha / Nilar အသံ၊ အင်တာနက်လိုတယ်။ |
| **Meta MMS (offline)** | အခမဲ့၊ ကိုယ့်ကွန်ပျူတာထဲမှာပဲ run တယ်၊ API key မလိုဘူး။ အသံက Edge ထက် စက်ရုပ်ဆန်တယ်၊ အသံတစ်မျိုးတည်း။ |

**MMS ကို ပထမဆုံးသုံးမယ်ဆိုရင်:**
1. `INSTALL_MMS.bat` ကို တစ်ခါ run ပါ (torch + transformers သွင်းတာ၊ ~200 MB ကျော်)။
2. App ထဲမှာ **TTS provider → Meta MMS (offline)** ရွေးပါ။ အသံ model ကို ပထမအကြိမ် START မှာ huggingface.co ကနေ အလိုလို download လုပ်ပါတယ်။

**MMS မအောင်မြင်ရင် Edge TTS ကို အလိုအလျောက် ပြန်သုံးပါတယ်:**
- torch မသွင်းရသေးဘူး / model download မရဘူး ဆိုရင် → အစအဆုံး Edge TTS နဲ့ ဆက်လုပ်မယ် (log မှာ ⚠️ ပြမယ်)။
- MMS က စာကြောင်းတစ်ကြောင်းမှာ error ဖြစ်ရင် → အဲဒီစာကြောင်းကိုပဲ Edge TTS က ပြောမယ်၊ ကျန်တာ MMS ဆက်ပြောမယ်။ MMS ရွေးထားရင် "Edge TTS Voice" က **Fallback Edge Voice** ဖြစ်သွားပါတယ်။
- Edge က ပြောခဲ့တဲ့ စာကြောင်းတွေကို နောက်တစ်ခါ START / RESUME နှိပ်ရင် MMS ကို ပြန်စမ်းပါတယ် (MMS ပြင်ပြီးရင် အဲဒါတွေ MMS အသံဖြစ်သွားမယ်)။
- Edge TTS ကို ရွေးထားရင်တော့ အရင်အတိုင်း — MMS ကို လုံးဝ မခေါ်ပါဘူး။

MMS အကြောင်း သိထားသင့်တာ:
- **License:** Meta MMS model ကို စီးပွားဖြစ်သုံးခွင့် မပေးထားဘူး (CC-BY-NC 4.0) လို့ မှတ်မိပါတယ်။ ဗီဒီယိုတွေကို ဝင်ငွေရအောင် တင်မယ်ဆိုရင် [model စာမျက်နှာ](https://huggingface.co/facebook/mms-tts-mya) မှာ license ကို အရင်စစ်ပါ။
- ဂဏန်းတွေကို တစ်လုံးချင်း ဖတ်ပါတယ် (၂၀၂၅ → နှစ် သုည နှစ် ငါး)၊ ပမာဏဂဏန်းတွေကို စာလုံးနဲ့ ရေးပေးမှ ပိုမှန်မယ်။ Pitch ချိန်လို့မရဘူး၊ Speed slider က သုံးလို့ရတယ်။
- Edit Text ကနေ စာပြင်ပြီး ပြန် START လုပ်ရင် ပြင်တဲ့စာကြောင်းပဲ အသံပြန်ထုတ်ပါတယ် (အသံတူတူပဲ ပြန်ထွက်အောင် seed ပုံသေထားတယ်)။
- Provider ပြောင်းရင် အသံအကုန် ပြန်ထုတ်ပါမယ် (အသံမတူလို့ cache မရောအောင်)။

## Smart Sync ဘယ်လိုအလုပ်လုပ်လဲ

- **ရုပ်ကို အပိုင်းခွဲ** — စာပိုင်းတိုင်းက မူရင်း video ရဲ့ ရုပ်တစ်ပိုင်းကို ပိုင်တယ်။ စာပိုင်း ၂ ခုကြားက အသံတိတ်နေရာကို အလယ်ကနေ ခွဲပြီး ဘေးက စာပိုင်း ၂ ခုကို ဝေပေးတယ်။ Video ရဲ့ ပထမ frame ကနေ နောက်ဆုံး frame အထိ ဘာမှ မကျန်ပါဘူး (V2 full coverage)။
- **အရှည်ကို အသံနဲ့ ညှိ** — ရုပ်တစ်ပိုင်းစီကို မြန်မာအသံ အရှည်အတိုင်း ဖြစ်အောင် နှေးတာ / မြန်တာ (`setpts`) လုပ်တယ်။
- **အမြန်ဆုံး ၁.၂၅ ဆ** — ရုပ်ကို ၁.၂၅ ဆထက် ပိုမမြန်စေဘူး (`max_video_speed`)။ အသံက ဒီထက်တိုနေသေးရင် အဲ့အပိုင်းရဲ့ နောက်ဆုံးက ရုပ်နည်းနည်းကို ဖြတ်တယ်။ အသံက ပိုရှည်ရင် ရုပ်ကို နှေးပေးတယ်။
- **Frame ကို တွဲတွက်** — အပိုင်းတိုင်းရဲ့ frame အရေအတွက်ကို အသံရဲ့ စုစုပေါင်း အချိန်နဲ့ တွက်တယ် (30 fps)။ အပိုင်း ရာနဲ့ချီ ရှိနေတောင် ရုပ်နဲ့ အသံ frame တစ်ဝက်ထက် ပိုမကွာဘူး။ အဆုံးမှာ log က `SYNC OK: picture=… narration=… diff=…` လို့ ပြပါတယ်။
- **ပုံစံ (Ratio / Fill)** — NVIDIA ရှိရင် NVENC၊ မရှိရင် libx264 နဲ့ ထုတ်တယ်။

  | Ratio | Video အရွယ် |
  |---|---|
  | 16:9 (default) | 1920×1080 |
  | 9:16 (TikTok / Reels / Shorts) | 1080×1920 |
  | 1:1 | 1080×1080 |
  | Original | မူရင်း video ရဲ့ ပုံစံအတိုင်း (အရှည်ဘက် အများဆုံး 1920) |

  မူရင်းနဲ့ ပုံစံမတူရင် (ဥပမာ 16:9 video ကို 9:16 လုပ်ရင်) **Fill** နဲ့ ရွေးပါ:
  - **Blur background** — ပုံတစ်ခုလုံး မြင်ရပြီး ဘေးကွက်လပ်မှာ အဲ့ပုံကိုပဲ ဝါးပြီး ဖြည့်တယ်။
  - **Black bars** — ဘေးကွက်လပ်ကို အမည်းနဲ့ ဖြည့်တယ်။
  - **Crop to fill** — ပုံကို ချဲ့ပြီး frame ပြည့်အောင် လုပ်တယ်။ ဘေးက ပိုတဲ့အပိုင်းကို ဖြတ်တယ်။

  Zoom / Flip နဲ့ Title၊ Logo၊ Blur box တွေက ရွေးထားတဲ့ Ratio အတိုင်း ထွက်ပြီး preview မှာလည်း ဒီအတိုင်း ပြတယ်။

## Gemini key နဲ့ ကန့်သတ်ချက်

- Gemini ကို **ဘာသာပြန်ဖို့ပဲ** သုံးတယ်။ English ကို စာသားပြောင်းတာက စက်ထဲမှာ Whisper နဲ့ လုပ်တယ်။
- အခမဲ့ key မှာ တစ်ရက်ကို သုံးလို့ရတဲ့ အကြိမ်ရေ ကန့်သတ်ထားတယ် (Google project တစ်ခုချင်းစီ အလိုက်)။ ပြည့်ရင်:
  - နောက် key ကို အလိုလို ပြောင်းတယ်။
  - Key တွေ အကုန်ပြည့်ရင် နောက် model ကို ပြောင်းတယ် (`gemini-3.5-flash → 3.5-flash-lite → 3.6-flash → 3.7-flash → 3.1-flash-lite`)။
  - အကုန်ပြည့်သွားရင် ရပ်သွားပေမဲ့ ပြီးသမျှ မပျောက်ဘူး။ နောက်နေ့ (သို့) key အသစ်ထည့်ပြီး **START / RESUME** နှိပ်ရင် ရပ်ခဲ့တဲ့နေရာကနေ ဆက်တယ်။
- Gemini ကို VPN / proxy နဲ့မှ သုံးလို့ရတဲ့ စက်ဆိုရင် `.env` ထဲမှာ `GEMINI_PROXY=http://127.0.0.1:10808` (ကိုယ့် proxy လိပ်စာ) ထည့်ပါ။ `127.0.0.1:10808` (v2rayN) ဖွင့်ထားရင် အလိုလို သုံးပါတယ်။ အမြဲ တိုက်ရိုက်ပဲ သုံးချင်ရင် `GEMINI_PROXY=none` ထည့်ပါ။ Edge TTS ကတော့ proxy မသုံးဘဲ တိုက်ရိုက် အရင်စမ်းပါတယ်။

## အဆင့်မြင့် ပြင်ဆင်ချက် (`config.json`)

Tool ဖွင့်ပြီး START နှိပ်လိုက်ရင် `config.json` ကို အလိုလို ဖန်တီးပေးပါတယ် (UI မှာ ရွေးထားတာတွေ သိမ်းဖို့ပါ)။ လိုမှပဲ ပြင်ပါ:

| Key | Default | အဓိပ္ပာယ် |
|---|---|---|
| `ffmpeg_path`, `ffprobe_path` | (အလိုလို ရှာ) | FFmpeg ဖိုင် လမ်းကြောင်း |
| `python_path` | (အလိုလို ရှာ) | `RUN.bat` သုံးမယ့် Python |
| `max_video_speed` | `1.25` | ရုပ်ကို မြန်စေနိုင်တဲ့ အများဆုံး ဆ |
| `translation_batch_max_items` | `40` | Gemini တစ်ခါမေးရင် ပါမယ့် စာပိုင်းအရေအတွက် |
| `atomic_target_duration`, `atomic_max_duration` | `4.2`, `5.6` | စာပိုင်းတစ်ပိုင်းရဲ့ အရှည် (စက္ကန့်) |
| `translation_audit` | `true` | ပြန်ပြီးတိုင်း စစ်ဆေးတဲ့ အဆင့် |
| `title_font_path` | `C:\Windows\Fonts\mmrtext.ttf` | Title / Extra text ဖောင့် |
| `overlay_blur_strength` | `18` | Blur box ရဲ့ ဝါးအား |

## စာကြောင်း ခွဲပုံ

English စာကို **စာကြောင်း (sentence) တစ်ကြောင်းချင်း** ခွဲပြီး ဘာသာပြန်ပါတယ် (VoxCPM recap လိုပါပဲ)။ စာကြောင်း တစ်ဝက်ကနေ မဖြတ်တော့လို့ Gemini က စာကြောင်းတစ်ကြောင်းကို နှစ်ခါ မပြောတော့ပါဘူး။ စာကြောင်းရှည်ရင် ကော်မာ (သို့) အသက်ရှူတဲ့ နေရာမှာ ဖြတ်ပါတယ် (အများဆုံး ၂၄ စက္ကန့်)။ Version အဟောင်းနဲ့ ဘာသာပြန်ပြီးသား job ကို resume လုပ်ရင်တော့ ဖြတ်ပုံဟောင်း (၄–၆ စက္ကန့်) နဲ့ပဲ ဆက်လုပ်ပါတယ် — ဘာသာပြန်ပြီးသားနဲ့ အသံတွေ မပျက်အောင်ပါ။

## စာသား ပြင်နည်း (Edit Text)

ဘာသာပြန်ပြီးသွားရင် **Edit Text** နှိပ်ပြီး စာကြောင်းတိုင်းရဲ့ English မူရင်းနဲ့ မြန်မာ narration ကို ဘေးချင်းယှဉ် ကြည့်ပြီး ပြင်လို့ရပါတယ်။
- **Prev / Next / Go** — စာကြောင်း ရွှေ့ကြည့်ပါ။ **Next problem** — English စာလုံး၊ တခြားဘာသာ စာလုံး ရောနေတဲ့ စာကြောင်းကို ရှာပေးပါတယ်။
- ပြင်ပြီး **Save** နှိပ်ပါ → **START / RESUME** နှိပ်ရင် ပြင်ထားတဲ့ စာကြောင်းကိုပဲ အသံ အသစ်ထုတ်ပြီး ကျန်တာ ပြန်သုံးပါတယ်။
- Render လုပ်နေရင်း စာကြောင်းတစ်ကြောင်း အသံထွက်မလာလို့ ရပ်သွားရင် (ဥပမာ English နဲ့ မြန်မာ ရောနေလို့) ဘယ်စာကြောင်းမှာ ရပ်လဲ ပြပြီး Edit Text ကို အဲ့စာကြောင်းမှာ ဖွင့်ပေးပါတယ်။

## ပြဿနာ ဖြေရှင်းနည်း

| တွေ့ရတာ | လုပ်ရမယ့်အရာ |
|---|---|
| `Python with the required packages was not found` | `INSTALL_REQUIREMENTS.bat` ကို ပြန် run ပါ။ Python 3.12 ကို PATH ထဲ ထည့်ထားဖို့ လိုပါတယ်။ |
| `Gemini API key မတွေ့ပါ` | `.env` ရှိမရှိ၊ `GEMINI_API_KEY=` နောက်မှာ key ပါမပါ စစ်ပါ။ UI ရဲ့ **Gemini .env** မှာ မှန်ကန်တဲ့ ဖိုင်ကို ရွေးပါ။ |
| `key pool exhausted` / 429 | ဒီနေ့ ကန့်သတ်ချက် ပြည့်သွားလို့ပါ။ Key ထပ်ထည့်ပါ (သို့) နောက်နေ့ **START / RESUME** နှိပ်ပါ။ |
| `open() got an unexpected keyword argument 'metadata_errors'` | `av` version အသစ် (19) ကြောင့်ပါ။ Repo အသစ်ကို ပြန် download လုပ်ပြီး `INSTALL_REQUIREMENTS.bat` ကို ပြန် run ပါ (`av==18.0.0` ကို သွင်းပေးပါမယ်)။ |
| Log မှာ `GPU Whisper failed … using the CPU instead` | NVIDIA GPU ရှိပေမဲ့ CUDA 12 library (cuBLAS/cuDNN) မရှိလို့ CPU နဲ့ ဆက်လုပ်တာပါ။ အလုပ်ပြီးပါတယ်၊ နည်းနည်းပဲ ပိုကြာပါတယ်။ |
| `You are sending unauthenticated requests to the HF Hub. Please set a HF_TOKEN…` ပြပြီး ရပ်နေသလို ဖြစ်နေတယ် | HF token **မလိုပါဘူး**။ Warning သက်သက်ပါ။ ပထမဆုံးအကြိမ်မှာ Whisper model (~460 MB) ကို download လုပ်နေတာပါ။ Log မှာ `⬇️ Whisper model: … MB downloaded` လို့ ၅ စက္ကန့်တစ်ခါ ပြပါတယ်။ တစ်ခါပဲ download လုပ်ရပါတယ်။ huggingface.co မဖွင့်ရတဲ့ စက်ဆိုရင် VPN သုံးပါ (သို့) `.env` ထဲမှာ `HF_ENDPOINT=https://hf-mirror.com` ထည့်ပါ။ |
| Edge TTS `NoAudioReceived` | Internet ကို စစ်ပါ။ Tool က တိုက်ရိုက် ၂ ကြိမ်၊ system proxy နဲ့ ၂ ကြိမ် ပြန်စမ်းပါတယ်။ English စာလုံး ရောနေတဲ့ စာကြောင်းဆိုရင် English စာလုံးတွေ ချန်ပြီး တစ်ခါ ထပ်စမ်းပါတယ်။ |
| `403, message='Invalid response status'` (`WSServerHandshakeError`) | Microsoft ရဲ့ အသံ service က ချိတ်ဆက်မှုကို ငြင်းတာပါ — VPN / proxy server တော်တော်များများကို ငြင်းပါတယ်။ **VPN ဖွင့်ထားရင် ပိတ်ပါ** (သို့) server ပြောင်းပါ။ ကွန်ပျူတာ နာရီ/Time zone ကို Settings → Time & language → Set time automatically နဲ့ မှန်အောင်ထားပါ။ မရသေးရင် `INSTALL_REQUIREMENTS.bat` ကို ပြန် run ပါ (edge-tts ကို update လုပ်ပါတယ်)။ ပြီးရင် **START / RESUME**။ VPN မပါရင် မရတဲ့ network ဆိုရင် `.env` ထဲမှာ `EDGE_TTS_PROXY=http://127.0.0.1:<port>` ထည့်ပါ။ |
| `ဒီဗီဒီယိုမှာ English စကား မကြားရပါဘူး` (သို့) `whisper_transcript.txt` ထဲမှာ "I'm not going to do it." လို စာကြောင်း တူတူတွေ ထပ်ခါထပ်ခါ ရေးထားပြီး မြန်မာအသံ မှားထွက်တယ် | ဗီဒီယိုက English စကား မဟုတ်လို့ပါ (တရုတ် / ဟိန္ဒီ / ကိုရီးယား …)။ ဒီ tool က **English ပြောတဲ့ ဗီဒီယိုအတွက်ပဲ** ဖြစ်ပါတယ် — English Whisper က တခြားဘာသာကို မကြားဘဲ English စာကြောင်း အနည်းငယ်ကို ထပ်ခါထပ်ခါ ရေးပါတယ်။ အခု version က ဘာသာပြန်မစခင် ရပ်ပြီး ပြောပေးပါတယ်။ English ဗီဒီယို ဖြစ်ပါလျက် ဒီ error တက်ရင် `whisper_transcript.txt` ကို စစ်ပါ (သီချင်း / ဆူညံသံ များတာ ဖြစ်နိုင်ပါတယ်)။ |
| `Edge TTS FAILED at segment 123` | အဲ့စာကြောင်းမှာ အသံ မထွက်လို့ ရပ်တာပါ။ **Yes** နှိပ်ရင် Edit Text ပွင့်လာပါမယ် — မြန်မာလို ပြင်ပြီး Save → **START / RESUME**။ |
| `Gemini JSON response failed after 3 attempts` | Gemini ရဲ့ အဖြေ ပျက်နေတာပါ။ **START / RESUME** ပြန်နှိပ်ရင် ဆက်လုပ်ပါတယ်။ (Story context အဆင့်မှာဆိုရင် အခု version က အဲ့အပိုင်းကို ချန်ပြီး ဆက်သွားလို့ မရပ်တော့ပါ။) |
| `[WinError 2] The system cannot find the file specified` (သို့) `ffmpeg.exe မတွေ့ပါ` (Preview မှာ `00:00 / 00:00`) | FFmpeg မရှိလို့ပါ။ `INSTALL_REQUIREMENTS.bat` ကို ပြန် run ပါ (FFmpeg ကို `ffmpeg\` ထဲ ထည့်ပေးပါမယ်)။ (သို့) gyan.dev ကနေ download လုပ်ပြီး `ffmpeg.exe`၊ `ffprobe.exe` ကို `RUN.bat` ဘေးက `ffmpeg` folder ထဲ ထည့်ပါ။ |
| Title မြန်မာစာ မပေါ်ဘူး | `py -3.12 -m playwright install chromium` ကို run ပါ။ ဖောင့်ကို `RECAP_MM_FONT` (environment variable) (သို့) `title_font_path` နဲ့ ပြောင်းလို့ရပါတယ်။ |
| Log မှာ `⚠️ ID 00012: removed letters of another script` | Gemini က မြန်မာစာထဲ တခြားဘာသာ စာလုံး ထည့်ခဲ့လို့ ဖယ်ထားတာပါ။ အဲ့စာကြောင်းကို `timestamp_translations.json` ထဲမှာ ကြည့်ပါ။ |

## Test

```bat
py -3.12 -m unittest discover -s tests
```
Internet မလိုပါဘူး။ Gemini ကို အတုနဲ့ အစားထိုး စမ်းပါတယ်။

## သတိပြုရန်

- Edge TTS က Microsoft ရဲ့ online ဝန်ဆောင်မှုပါ။ Gemini ကတော့ Google ရဲ့ API ပါ။
- သူတို့ရဲ့ စည်းကမ်းချက်တွေကို လိုက်နာပါ။
- သုံးမယ့် video ရဲ့ မူပိုင်ခွင့်ကို ကိုယ်တိုင် တာဝန်ယူပါ။

---

## English

**KG ReMovie version 3.0** (English / Chinese → Myanmar) turns an English-narrated recap/story video into a Myanmar-narrated one
on Windows.

### How it works
1. **Listen** — local Whisper (`small.en`, faster-whisper; NVIDIA GPU or CPU) writes the English
   with word timestamps.
2. **Split** — sentence/clause/pause boundaries give short sync units (about 4.2 s, at most 5.6 s);
   more units = more sync anchors.
3. **Story memory** — Gemini reads the whole transcript first and keeps names, relationships and
   places consistent.
4. **Translate** — Gemini translates 40 units per request into natural spoken Burmese narration
   (no summary, no shortening, every unit keeps its own content), then an audit pass repairs
   omissions/shifts/duplicates. Letters of another script inside the Burmese (e.g. Georgian "მის"
   inside "ဧည့်ခန်း") are asked again, and if still there removed and logged.
5. **Voice** — Microsoft Edge TTS Myanmar voices (Thiha / Nilar). "Short pauses" trims the silence
   Edge puts around each clip (~0.25 s between lines instead of ~1 s).
6. **Smart Sync** — every unit owns a window of the original picture (the silence between two units
   is split at its middle, so the whole video is used). Each window is slowed down or sped up to the
   length of its Myanmar voice; it never plays faster than 1.25× (`max_video_speed`), and when the
   voice is shorter still the end of that window is cut. Frame counts are cumulative at 30 fps, so
   even hundreds of parts stay within half a frame of the voice (`SYNC OK … diff=…` in the log).
   Output ratio **16:9** (1920×1080), **9:16** (1080×1920), **1:1** (1080×1080) or **Original**
   (the source shape, long side at most 1920); when the source has another shape, **Fill** decides:
   Blur background, Black bars or Crop to fill. Optional zoom/flip; NVENC or libx264.
7. **Production tools** — blur boxes, title, logo and an extra text box placed on the preview.

The output has only the Myanmar voice (no original audio or music).

### Requirements
Windows 10/11 64-bit · Python 3.12 64-bit (with tcl/tk, on PATH) · FFmpeg (`ffmpeg.exe` +
`ffprobe.exe` on PATH, in `C:\ffmpeg\bin`, or in a folder named `ffmpeg` here) · a free Gemini API
key ([aistudio.google.com/apikey](https://aistudio.google.com/apikey)) · internet. An NVIDIA GPU is
optional (without the CUDA 12 libraries Whisper falls back to the CPU by itself).

### Install
1. Download the repo (Code → Download ZIP) and unzip it.
2. Run **`INSTALL_REQUIREMENTS.bat`** (pip packages, Chromium for the Myanmar title renderer, and
   FFmpeg: when it is not on PATH or in `C:\ffmpeg\bin`, about 100 MB is downloaded into `ffmpeg\`).
   `[WinError 2] The system cannot find the file specified` means FFmpeg is missing — run it again.
3. Copy **`.env.example`** to **`.env`** and set `GEMINI_API_KEY=`. More keys
   (`GEMINI_IMAGE_PROJECT_1_KEY`, `GEMINI_IMAGE_PROJECT_2_KEY`, …) are used in turn when one is used
   up; after all keys the next model is tried
   (`gemini-3.5-flash → 3.5-flash-lite → 3.6-flash → 3.7-flash → 3.1-flash-lite`).
   If Gemini needs a proxy, add `GEMINI_PROXY=http://host:port` (a running v2rayN on
   `127.0.0.1:10808` is used automatically; `GEMINI_PROXY=none` forces direct).

Never share or commit your `.env` (it is in `.gitignore`).

The first run downloads the Whisper model (~460 MB) from huggingface.co; the log shows
`⬇️ Whisper model: … MB downloaded`. No account or HF_TOKEN is needed — the "unauthenticated
requests" line is only a warning. If huggingface.co does not open, use a VPN or set
`HF_ENDPOINT=https://hf-mirror.com` in `.env`.

### Use
Double-click **`RUN.bat`**:
- **Source Video** → Browse (or **Folder** for a batch; finished videos are skipped).
- **Edge TTS Voice / Speed** on the left.
- **Production Tools** in the middle: Zoom, Flip, Voice vol, Short pauses, Ratio + Fill, blur,
  title, logo, extra text.
- **Preview** on the far right: seek, Refresh Frame, drag the title/logo/text, draw blur boxes.
- **START / RESUME** — starts or continues; **STOP SAFELY** — stops at a safe point and keeps
  everything; **Output Video**; **Edit Text** — read each English line next to its Burmese narration,
  fix the Burmese and Save; START / RESUME then re-voices only the edited lines. When a line gets no
  audio (e.g. English and Burmese mixed), the error names the line and offers to open Edit Text on it.
- Lines are whole English sentences (like the VoxCPM recap tool), so a sentence is never cut in two and told
  twice; a long sentence ends at a comma or a breath (24 s at most). A job translated with an older version
  keeps its 4-6 s lines when resumed.
- English-speaking videos only: on Chinese / Hindi / Korean … speech the English Whisper writes a few English
  phrases again and again ("I'm not going to do it." ×40) and the narration comes out wrong; when a quarter of
  the Whisper lines repeat, the job now stops before translating and says so.
- Edge TTS `403 Invalid response status`: Microsoft refuses many VPN / proxy servers — turn the VPN off (or
  change server), set the Windows clock automatically, or run INSTALL_REQUIREMENTS.bat again; on a network that
  needs a proxy put `EDGE_TTS_PROXY=http://127.0.0.1:<port>` in the .env.

Result: `output\<name>_<code>\edge_tts_smart_sync\final_edge_tts_smart_sync.mp4`
(plus `whisper_transcript.txt`, `timestamp_translations.json`, `smart_sync_plan.json`, `run.log`).

### Advanced (`config.json`, created on the first START)
`ffmpeg_path`, `ffprobe_path`, `python_path`, `max_video_speed` (1.25),
`translation_batch_max_items` (40), `atomic_target_duration` / `atomic_max_duration` (4.2 / 5.6),
`translation_audit` (true), `title_font_path`, `overlay_blur_strength` (18).

### Tests
`py -3.12 -m unittest discover -s tests` (offline; Gemini is mocked).

### Notes
Edge TTS is a Microsoft online service and Gemini is a Google API — follow their terms. You are
responsible for the rights to the videos you process.


---

## New: Chinese → Myanmar dubbing and Orynx

**Chinese (中文) → Myanmar.** Pick **Source language → `Chinese 中文 → Myanmar`** in the settings pane and press
START. Everything after the transcript is the same as for English (story memory, translation, audit, Edge TTS voice,
Smart Sync). Differences: a multilingual Whisper model (`small`, ~480 MB; set `"whisper_model_zh": "medium"` in
`config.json` for more accuracy), lines are cut at `。！？` / `，、；：`, names are written in Burmese letters by their
Mandarin pronunciation with one fixed spelling per name, idioms are translated by meaning, and a video with no Chinese
speech stops before any AI request. Chinese jobs live in their own `output\<video>_<code>_zh` folder.

**Orynx (https://orynx.dev).** Put `ORYNX_API_KEY=` next to (or instead of) `GEMINI_API_KEY=` in `.env`. By default
Gemini goes first and Orynx takes over when all Gemini keys/models are exhausted (429/quota/503/timeout); the same
request is re-sent. `TRANSLATION_PROVIDER_ORDER=orynx,gemini` puts Orynx first, `=orynx` uses Orynx only.
`ORYNX_API_KEY_2…` add more keys, `ORYNX_MODELS=` picks models, `ORYNX_BASE_URL=` / `ORYNX_PROXY=` are optional.
Orynx is reached through the Gemini-compatible endpoint with the same `google-genai` client.

**Freeze rhythm.** Production Tools → Video → *Freeze rhythm*: the picture plays for 5 / 8 / 10 s, then one frame is held
for 2 / 4 s while it eases in (Small / Medium / Large, random strength and focus point per hold), and so on. Picture
only: the audio and the video length are unchanged, titles / logo / blur boxes stay still on top, and the result for a
given video is repeatable (`"freeze_rhythm": {"seed": N}` in `config.json` changes it).

**TTS provider.** Settings → *TTS provider*: *Edge TTS* (default, unchanged) or *Meta MMS (offline)* — the free
`facebook/mms-tts-mya` model that runs on this PC without any key (run `INSTALL_MMS.bat` once for torch + transformers;
the model downloads on first use). With MMS selected, Edge TTS is the automatic fallback: if MMS cannot load, every
line is spoken by Edge; if MMS fails on a line, only that line is. Lines Edge had to speak are tried with MMS again on
the next run. MMS is more robotic than Edge, has one voice, reads digits one by one, and its licence (CC-BY-NC 4.0, as
far as I remember) excludes commercial use - check the model page.
