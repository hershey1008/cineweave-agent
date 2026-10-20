"""Build a narrated screenshot walkthrough; never fabricates application responses."""
import json
import math
from pathlib import Path
import re
import subprocess
import wave

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
MEDIA=ROOT/'docs/media'
WORK=ROOT/'.runtime/video-build'
WORK.mkdir(parents=True,exist_ok=True)
WIDTH,HEIGHT=1920,1080
INK='#e6eddb'
MUTED='#a7baa6'
ACCENT='#dd8669'
FONT=Path('C:/Windows/Fonts/msyh.ttc')


def font(size):
    return ImageFont.truetype(str(FONT),size)


def wrap(text,size,max_width):
    f=font(size)
    lines=[]
    for paragraph in text.split('\n'):
        current=''
        for char in paragraph:
            if f.getlength(current+char)>max_width and current:
                lines.append(current);current=char
            else:
                current+=char
        lines.append(current)
    return lines


def card(scene,index,subtitle):
    canvas=Image.new('RGB',(WIDTH,HEIGHT),'#10251f')
    draw=ImageDraw.Draw(canvas)
    draw.rectangle((0,0,620,HEIGHT),fill='#142d25')
    for ray in range(8):
        angle=ray*math.pi/4
        draw.line((77+8*math.cos(angle),83+8*math.sin(angle),77+23*math.cos(angle),83+23*math.sin(angle)),fill=ACCENT,width=3)
    draw.text((114,52),'CineWeave',font=font(46),fill=INK)
    draw.text((61,118),'影织 · 多轮电影选片',font=font(24),fill=MUTED)
    draw.line((60,186,547,186),fill='#355044',width=2)
    draw.text((60,218),f'{index+1:02d} / 09   ACTUAL APP WALKTHROUGH',font=font(17),fill=ACCENT)
    y=275
    for line in wrap(scene['title'],44,490):
        draw.text((58,y),line,font=font(44),fill=INK);y+=66
    y+=38
    for point in scene['points']:
        draw.rounded_rectangle((61,y+13,69,y+21),radius=3,fill=ACCENT)
        for line in wrap(point,25,438):
            draw.text((89,y),line,font=font(25),fill=MUTED);y+=43
        y+=17
    draw.text((60,838),'真实 LLM  /  BGE-M3  /  推荐模型',font=font(20),fill='#819b88')
    draw.text((60,881),'真实界面截图剪辑 · 等待时间已省略',font=font(19),fill='#819b88')
    shot=Image.open(MEDIA/'screenshots'/f"{scene['image']}.png").convert('RGB')
    shot.thumbnail((1210,876),Image.Resampling.LANCZOS)
    x=650+(1210-shot.width)//2;y=40+(876-shot.height)//2
    draw.rounded_rectangle((x-7,y-7,x+shot.width+7,y+shot.height+7),radius=13,fill='#607264')
    canvas.paste(shot,(x,y))
    draw.rectangle((0,952,WIDTH,HEIGHT),fill='#0a1915')
    lines=wrap(subtitle,30,1770)
    for n,line in enumerate(lines[:2]):
        draw.text(((WIDTH-font(30).getlength(line))/2,978+n*44),line,font=font(30),fill='#eef2e7')
    draw.rectangle((0,1074,int(WIDTH*(index+1)/9),1080),fill=ACCENT)
    return canvas


def stamp(seconds):
    ms=round(seconds*1000)
    h,ms=divmod(ms,3600000);m,ms=divmod(ms,60000);s,ms=divmod(ms,1000)
    return f'{h:02}:{m:02}:{s:02},{ms:03}'


def main():
    plan=json.loads((MEDIA/'video-plan.json').read_text(encoding='utf-8'))
    audio=[];parts=[];srt=[];elapsed=0;sample_rate=None
    for index,scene in enumerate(plan['scenes']):
        path=ROOT/'.runtime/video-audio'/f"{scene['id']}.wav"
        with wave.open(str(path),'rb') as stream:
            rate=stream.getframerate();channels=stream.getnchannels();width=stream.getsampwidth()
            assert channels==1 and width==2,'Expected mono PCM16 narration'
            samples=np.frombuffer(stream.readframes(stream.getnframes()),dtype='<i2').copy()
        sample_rate=rate if sample_rate is None else sample_rate
        assert rate==sample_rate
        # Hold each chapter for a readable minimum; silence is explicitly part of the edit.
        duration=max(12.5,len(samples)/rate+0.6)
        padded=np.pad(samples,(0,round(duration*rate)-len(samples)))
        audio.append(padded)
        chunks=[c for c in re.split(r'(?<=[。！？])',scene['narration']) if c]
        total=sum(len(c) for c in chunks)
        for j,chunk in enumerate(chunks):
            seconds=duration*len(chunk)/total
            frame=WORK/f'{index:02}-{j:02}.png'
            card(scene,index,chunk).save(frame)
            parts.append(f"file '{frame.as_posix()}'\nduration {seconds:.6f}\n")
            srt.append(f'{len(srt)+1}\n{stamp(elapsed)} --> {stamp(elapsed+seconds)}\n{chunk}\n')
            elapsed+=seconds
        if index==0:
            card(scene,index,'多轮电影选片 Agent · 真实 LLM × 语义召回 × 个性化推荐').save(MEDIA/'demo-poster.jpg',quality=92)
    last=frame
    playlist=WORK/'frames.txt'
    playlist.write_text(''.join(parts)+f"file '{last.as_posix()}'\n",encoding='utf-8')
    (MEDIA/'cineweave-demo.zh-CN.srt').write_text('\n'.join(srt),encoding='utf-8')
    audio_path=WORK/'narration.wav'
    with wave.open(str(audio_path),'wb') as stream:
        stream.setnchannels(1);stream.setsampwidth(2);stream.setframerate(sample_rate)
        stream.writeframes(np.concatenate(audio).astype('<i2').tobytes())
    output=MEDIA/'cineweave-demo.mp4'
    cmd=[imageio_ffmpeg.get_ffmpeg_exe(),'-y','-hide_banner','-loglevel','warning',
        '-f','concat','-safe','0','-i',str(playlist),'-i',str(audio_path),
        '-vf','fps=24,format=yuv420p','-c:v','libx264','-preset','medium','-crf','25',
        '-c:a','aac','-b:a','128k','-t',f'{elapsed:.3f}','-movflags','+faststart',str(output)]
    subprocess.run(cmd,check=True)
    report={'method':plan['method'],'width':WIDTH,'height':HEIGHT,'fps':24,'duration_seconds':round(elapsed,3),
        'chapters':len(plan['scenes']),'voice':'Microsoft Huihui local TTS','bytes':output.stat().st_size,
        'codec':'H.264 + AAC','recording_date':'2026-10-20','captions':'cineweave-demo.zh-CN.srt'}
    (MEDIA/'video-manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':
    main()
