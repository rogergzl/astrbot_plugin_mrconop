"""
MRCon Web 管理面板 - 基于原生 asyncio TCP 服务器
特性：serve_forever 运行 / 密码登录 / Session 管理 / 11 功能模块 SPA
"""
import asyncio
import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import datetime
from pathlib import Path
from html import escape
from typing import Dict, List, Optional, Set, Tuple, Any
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

from astrbot.api import logger
from ..core.transport import get_pool

# ==============================================================
# 前端 SPA 模板 — 密码登录 + 11 Tab
# ==============================================================
PANEL_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>MRCon 管理面板</title>
<style>
:root{--bg:#1a1a2e;--c:#16213e;--b:#0f3460;--a:#e94560;--t:#e0e0e0;--m:#aaa;--s:#2ecc71;--w:#f39c12;--d:#e74c3c;--p:#9b59b6;--i:#1abc9c}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:var(--bg);color:var(--t);min-height:100vh;display:flex}
.sb{width:220px;min-width:220px;background:var(--c);border-right:1px solid var(--b);padding:16px 0;display:none;flex-direction:column}
.sb h2{font-size:15px;color:var(--a);padding:0 18px 14px;border-bottom:1px solid var(--b);margin-bottom:8px}
.sb .ver{font-size:10px;color:var(--m);margin-left:6px}
.sb nav{flex:1;overflow-y:auto}
.sb nav a{display:flex;align-items:center;gap:8px;padding:11px 18px;color:var(--m);text-decoration:none;font-size:13px;transition:.15s;border-left:3px solid transparent}
.sb nav a:hover{color:var(--t);background:rgba(233,69,96,.06)}
.sb nav a.on{color:var(--a);background:rgba(233,69,96,.1);border-left-color:var(--a)}
.sb .ft{padding:14px 18px;font-size:10px;color:#555;border-top:1px solid var(--b);margin-top:auto}
.ma{flex:1;display:none;flex-direction:column;min-width:0}
.ma header{background:var(--c);padding:12px 24px;border-bottom:1px solid var(--b);display:flex;align-items:center;justify-content:space-between;font-size:13px}
.ma header .pt{color:var(--a)}
.ma main{flex:1;padding:24px;overflow-y:auto;max-width:none}
.ct{background:var(--c);border-radius:8px;padding:20px 22px;margin-bottom:16px;border:1px solid var(--b);break-inside:avoid}
.ct h3{font-size:15px;color:var(--a);margin-bottom:14px;display:flex;align-items:center;gap:8px}
.sts{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px;margin-bottom:16px}
.st{background:var(--bg);border-radius:6px;padding:14px 16px;text-align:center;cursor:pointer;transition:background .15s}.st:hover{background:rgba(233,69,96,.08)}
.st .n{font-size:26px;font-weight:700;color:var(--a)}
.st .l{font-size:11px;color:var(--m);margin-top:4px}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:8px 12px;text-align:left;border-bottom:1px solid var(--b);white-space:nowrap}
th{color:var(--m);font-weight:600;font-size:11px;text-transform:none;letter-spacing:.5px}
tr:hover{background:rgba(233,69,96,.04)}
td{word-break:break-all;max-width:300px}
.t1{display:inline-block;padding:2px 8px;border-radius:3px;font-size:10px}
.t-on{background:rgba(46,204,113,.15);color:var(--s)}.t-off{background:rgba(231,76,60,.15);color:var(--d)}
.t-p{background:rgba(243,156,18,.15);color:var(--w)}.t-a{background:rgba(46,204,113,.15);color:var(--s)}.t-r{background:rgba(231,76,60,.15);color:var(--d)}
button{border:none;border-radius:4px;cursor:pointer;font-size:12px;transition:.15s;display:inline-flex;align-items:center;gap:5px}
.bs{padding:6px 14px}.bsm{padding:4px 10px;font-size:11px}
.b1{background:var(--a);color:#fff}.b1:hover{background:#c73a52}
.b2{background:var(--b);color:var(--t)}.b2:hover{background:#1a4a7a}
.bd{background:rgba(231,76,60,.2);color:var(--d)}.bd:hover{background:rgba(231,76,60,.4)}
.bg{background:rgba(46,204,113,.2);color:var(--s)}.bg:hover{background:rgba(46,204,113,.4)}
.bw{background:rgba(243,156,18,.2);color:var(--w)}.bw:hover{background:rgba(243,156,18,.4)}
.bp{background:rgba(155,89,182,.2);color:var(--p)}.bp:hover{background:rgba(155,89,182,.4)}
input,select,textarea{background:var(--bg);border:1px solid var(--b);border-radius:4px;padding:7px 10px;color:var(--t);font-size:13px;width:100%}
input:focus,select:focus,textarea:focus{outline:none;border-color:var(--a)}
.fg{margin-bottom:12px}.fg label{display:block;font-size:11px;color:var(--m);margin-bottom:4px}
.fr{display:flex;gap:10px;align-items:end}.fr .fg{flex:1}
.if{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.badge{display:inline-block;background:rgba(233,69,96,.12);color:var(--a);padding:2px 8px;border-radius:3px;font-size:10px;margin-left:6px}
.toast{position:fixed;bottom:24px;right:24px;padding:12px 20px;border-radius:6px;font-size:13px;z-index:9999;animation:fi .3s}
.to{background:var(--s);color:#fff}.te{background:var(--d);color:#fff}
@keyframes fi{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
.mbg{position:fixed;inset:0;background:rgba(0,0,0,.65);display:flex;align-items:center;justify-content:center;z-index:998}
.mod{background:var(--c);border-radius:10px;padding:24px;min-width:540px;max-width:90vw;max-height:85vh;overflow-y:auto;border:1px solid var(--b)}
.mod h3{margin-bottom:18px;color:var(--a)}
.tg{position:relative;display:inline-block;width:40px;height:22px}
.tg input{opacity:0;width:0;height:0}
.tg .sl{position:absolute;cursor:pointer;inset:0;background:var(--b);border-radius:11px;transition:.3s}
.tg .sl:before{content:"";position:absolute;height:16px;width:16px;left:3px;bottom:3px;background:#fff;border-radius:50%;transition:.3s}
.tg input:checked+.sl{background:var(--a)}.tg input:checked+.sl:before{transform:translateX(18px)}
.emp{text-align:center;padding:50px;color:#555;font-size:13px}
pre{background:var(--bg);padding:12px;border-radius:4px;font-size:12px;overflow-x:auto;max-height:300px;white-space:pre-wrap;word-break:break-all}
.fb{display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap}
.fbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:12px}
.fbar select,.fbar input{width:auto;min-width:120px}
.ac{display:flex;gap:6px}
/* Login */
.lc{position:fixed;inset:0;display:flex;align-items:center;justify-content:center;background:var(--bg);z-index:9999}
.lp{width:clamp(340px,90vw,400px);background:var(--c);border:1px solid var(--b);border-radius:10px;padding:32px 28px 36px}
.lp h1{margin:0 0 14px;font-size:24px;color:var(--a)}
.lp .mu{margin-bottom:20px;font-size:14px;color:var(--m)}
.lp form{display:flex;flex-direction:column;gap:16px}
.lp label{font-weight:600;color:var(--m);font-size:14px}
.lp input[type="password"]{padding:10px 14px;font-size:15px}
.lp button{margin-top:8px;width:100%;padding:11px}
.logout{padding:7px 14px;border-radius:4px;border:1px solid var(--b);color:var(--m);background:transparent;cursor:pointer;font-size:12px;transition:.15s}
.logout:hover{background:rgba(231,76,60,.15);color:var(--d);border-color:var(--d)}
/* Online cards */
.oc-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px}
.oc{background:var(--bg);border-radius:8px;padding:14px;display:flex;align-items:center;gap:12px;border:1px solid transparent;transition:.15s}
.oc:hover{border-color:var(--b)}
.oc-av{width:42px;height:42px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:16px;color:#fff;flex-shrink:0}
.oc-info{flex:1;min-width:0}
.oc-name{font-size:13px;font-weight:600;margin-bottom:4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.oc-dur{font-size:11px;color:var(--m);margin-bottom:4px}
.oc-bar{height:4px;background:var(--b);border-radius:2px;overflow:hidden}
.oc-bar-fill{height:100%;border-radius:2px;transition:width .5s}
.oh-chart{display:flex;align-items:flex-end;gap:8px;height:360px;padding:60px 80px 8px;overflow-x:auto;overflow-y:visible;min-width:100%}
.oh-bar{min-width:28px;border-radius:5px 5px 0 0;position:relative;flex-shrink:0;cursor:default;transition:opacity .15s}
.oh-bar:hover{opacity:.8;z-index:9999}
.oh-tip{display:none;position:absolute;top:-56px;left:50%;transform:translateX(-50%);background:#333;color:#fff;padding:6px 10px;border-radius:5px;font-size:11px;white-space:nowrap;z-index:99999;pointer-events:none;line-height:1.6;box-shadow:0 2px 8px rgba(0,0,0,.3)}
.oh-bar:hover .oh-tip{display:block;z-index:9999}
.oh-chart .oh-bar:first-child .oh-tip{left:0;transform:none}
.oh-chart .oh-bar:last-child .oh-tip{left:auto;right:0;transform:none}
/* Settings form */
.sf{}
.sg{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;align-items:stretch}
.sg-item{background:var(--bg);border:1px solid var(--b);border-radius:8px;padding:14px;display:flex;flex-direction:column}
.sg-item h4{margin:0 0 10px;font-size:13px;color:var(--w);padding-bottom:8px;border-bottom:1px solid var(--b);flex-shrink:0}
.sg-item .sg-body{flex:1;display:flex;flex-direction:column}
.sg-full{grid-column:1/-1}
.sf h4{font-size:13px;color:var(--w);margin:16px 0 8px;padding-top:12px;border-top:1px solid var(--b)}
.sf input[type="number"],.sf input[type="text"]{width:120px}
.sf textarea{min-height:80px;font-family:monospace;font-size:12px}
.sf select{width:160px}
/* Relay cards */
.rl-card{display:flex;align-items:center;padding:8px 12px;background:var(--c);border:1px solid var(--b);border-radius:6px;margin-bottom:6px;gap:8px;flex-wrap:wrap}
.rl-grp{font-weight:700;font-size:13px;min-width:180px}
.rl-arrow{color:var(--a);font-size:14px}
.rl-sel{background:var(--bg);border:1px solid var(--b);border-radius:4px;padding:5px 8px;color:var(--t);font-size:12px;max-width:130px}
.rl-ctrls{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.rl-lbl{font-size:11px;color:var(--m)}
.rl-row{display:flex;align-items:center;gap:6px;width:100%;margin-top:4px;flex-wrap:wrap}
.fmt-ed{display:flex;align-items:center;gap:4px;flex-wrap:wrap;padding:4px 6px;background:var(--bg);border:1px solid var(--b);border-radius:4px;min-height:28px}
.fmt-chip{display:inline-flex;align-items:center;padding:2px 7px;border-radius:3px;font-size:11px;cursor:pointer;transition:opacity .15s}
.fmt-chip:hover{opacity:.7}
.fmt-chip.fc-tx{background:rgba(255,255,255,.08);color:var(--t)}
.fmt-chip.fc-ph{background:rgba(147,112,219,.35);color:#d4bfff}
.fmt-chip.fc-ma{background:rgba(56,182,121,.35);color:#b5e8ce}
.fmt-add{display:inline-flex;align-items:center;gap:3px}
.fmt-add button{padding:2px 8px;font-size:10px;border-radius:3px;cursor:pointer;border:1px dashed var(--b);background:transparent;color:var(--m);white-space:nowrap}
.fmt-add button:hover{background:var(--t2);color:var(--t)}
.fmt-add .fa-cust{color:var(--s);font-weight:bold}
.fmt-row{display:flex;align-items:flex-start;gap:6px;flex-direction:column;width:100%}
.fmt-row .fmt-title{font-size:11px;color:var(--m);white-space:nowrap}
.qc-box{display:inline-flex;align-items:center;gap:2px}
.qc-tg{margin:0;vertical-align:middle}
.qc-off{opacity:.4;pointer-events:auto}
</style>
</head>
<body>
<div class="sb" id="sb">
  <h2>MRCon<span class="ver">v3.37.5</span></h2>
  <nav>
    <a href="#dashboard" class="on" data-tab="dashboard">📊 仪表盘</a>
    <a href="#servers" data-tab="servers">🖥️ 服务器管理</a>
    <a href="#relay" data-tab="relay">💬 群服互联</a>
    <a href="#tracker" data-tab="tracker">⏱️ 在线追踪</a>
    <a href="#players" data-tab="players">👤 玩家管理</a>
    <a href="#compensations" data-tab="compensations">🎁 补偿管理</a>
    <a href="#exchange" data-tab="exchange">💱 积分兑换</a>
    <a href="#lottery" data-tab="lottery">🎰 抽奖管理</a>
    <a href="#online" data-tab="online">🟢 在线列表</a>
    <a href="#audit" data-tab="audit">📋 审计日志</a>
    <a href="#macros" data-tab="macros">⚡ 宏命令</a>
    <a href="#scripts" data-tab="scripts">📜 脚本与触发器</a>
    <a href="#logviewer" data-tab="logviewer">📄 日志查看器</a>
    <a href="#cmd" data-tab="cmd">⚡ 快捷命令</a>
    <a href="#settings" data-tab="settings">⚙️ 全局设置</a>
  </nav>
  <div class="ft">端口 9949 | 本地管理</div>
</div>
<div class="ma" id="ma">
  <header><span class="pt" id="pt">仪表盘</span><div><button class="logout" onclick="dologout()">退出登录</button></div></header>
  <main id="main"></main>
</div>
<div id="login-root" class="lc" style="display:flex"><div class="lp"><h1>MRCon 控制台</h1><p class="mu">正在连接...</p></div></div>
<div id="toast" style="display:none"></div>
<script>
"use strict";
var A="/api",tab="dashboard",rf=null,idleTO=600,idleT=null,bgT=null;
function gn(srvs){if(!srvs||!srvs.length)return"";var n=srvs[0].name||srvs[0].server_name||"";return n}
var d=document;
function escapeHtml(s){if(!s)return"";return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;")}
var hx=escapeHtml;
function toast(m,e){var t=d.getElementById("toast");t.className="toast "+(e?"te":"to");t.textContent=m;t.style.display="block";setTimeout(function(){t.style.display="none"},2500)}
async function refLog(){try{await loLogViewer();toast("日志已刷新")}catch(e){toast("刷新失败: "+e.message,true)}}
async function testLogFile(){if(!_lv_server){toast("请先选择服务器",true);return}toast("正在检测...");try{var r=await fj(A+"/log-viewer/test?server="+encodeURIComponent(_lv_server));var h='';h+='<div class="mbg" onclick="if(event.target===this)this.remove()"><div class="mod" style="max-width:700px"><h3>🔍 日志检测: '+_lv_server+'</h3>';if(!r.ok){h+='<div style="padding:14px;border-radius:6px;background:rgba(231,76,60,.1);color:var(--d);margin:8px 0"><strong>❌ '+r.error+'</strong><br><small>'+r.hint+'</small></div>'}else{h+='<div style="color:var(--s);margin-bottom:8px">✅ '+r.summary+'</div>';if(r.paths){r.paths.forEach(function(p){h+='<div class="ct" style="margin-bottom:8px"><strong>📁 '+p.path+'</strong>';if(!p.exists){h+='<div style="color:var(--d)">❌ 文件不存在</div>'}else if(!p.readable){h+='<div style="color:var(--d)">❌ '+p.error+'</div>'}else{h+='<div style="font-size:11px;color:var(--m)">大小: '+(p.size/1024).toFixed(1)+' KB | 最后 '+p.lines+' 行可读</div>';if(p.sample&&p.sample.length){h+='<pre style="font-size:10px;max-height:200px;overflow:auto;background:var(--bg);padding:8px;border-radius:4px;margin-top:4px">'+p.sample.map(function(l){return escapeHtml(l)}).join('\n')+'</pre>'}}h+='</div>'})}}h+='<button class="b2 bs" onclick="document.querySelector(\'.mbg\').remove()">关闭</button></div></div>';document.body.insertAdjacentHTML("beforeend",h)}catch(e){toast("检测失败: "+e.message,true)}}
async function pj(u,d2){var r=await fetch(u,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(d2)});if(!r.ok)throw new Error(await r.text()||r.statusText);return await r.json()}
async function pjt(u,d2){var r=await fetch(u,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(d2)});if(!r.ok)throw new Error(await r.text()||r.statusText);return await r.json()}
async function fj(u,o){var r=await fetch(u,o);if(r.status===401){login();throw new Error("re-auth")}if(!r.ok)throw new Error(await r.text()||r.statusText);return await r.json()}
/* auth */
function login(m,e){
    var s=d.getElementById("sb"),a=d.getElementById("ma"),l=d.getElementById("login-root");
    s.style.display="none";a.style.display="none";l.style.display="flex";l.className="lc";
    l.innerHTML='<div class="lp"><h1>MRCon 控制台</h1><p class="mu">请输入管理密码</p>'+(m?'<div style="padding:10px;border-radius:6px;margin-bottom:12px;font-size:13px;background:'+(e?'rgba(231,76,60,.15)':'rgba(46,204,113,.15)')+';color:'+(e?'var(--d)':'var(--s)')+'">'+m+'</div>':'')+'<form onsubmit="return dologin()"><label>密码</label><input id="lpwd" type="password" required><button class="b1 bs" type="submit">进入面板</button></form><p style="margin-top:16px;font-size:11px;color:var(--m);text-align:center;line-height:1.6">如未设置管理密码，刷新网页即可重新进入面板</p></div>';
}
function showErr(msg){
    var l=d.getElementById("login-root");
    l.style.display="flex";l.className="lc";
    l.innerHTML='<div class="lp"><h1>MRCon 控制台</h1><p class="mu" style="color:var(--d)">'+msg+'</p><p style="font-size:10px;color:var(--m);word-break:break-all">按 F12 打开 Console 查看详情</p></div>';
}
async function dologin(){
    try{
        var r=await fetch(A+"/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({password:d.getElementById("lpwd").value})});
        if(r.ok){panel()}else{var t=await r.text();login("密码错误",true)}
    }catch(e){console.error("[MRCon] 登录失败:",e);login("连接失败: "+e.message+"<br><small>请检查网络或插件运行状态</small>",true)}
    return false
}
async function dologout(){await fetch(A+"/logout",{method:"POST"});login()}
async function chk(){
    try{
        var r=await fetch(A+"/auth");
        if(r.ok){panel()}else{login()}
    }catch(e){console.error("[MRCon] 认证检查失败:",e);showErr("连接失败: "+e.message+"<br><small>请确认插件已启动且Web面板端口可达</small>")}
}
function panel(){
    d.getElementById("login-root").style.display="none";
    d.getElementById("sb").style.display="flex";
    d.getElementById("ma").style.display="flex";
    load(tab||"dashboard")
}
function nav(t){if(tab==='settings'&&t!=='settings'&&document.getElementById('cfg-form')){doSaveCfg().catch(function(e){toast("自动保存失败: "+e.message,true)})}tab=t;document.getElementById("pt").textContent=document.querySelector('[data-tab="'+t+'"]').textContent.trim();document.querySelectorAll(".sb nav a").forEach(function(a){a.classList.toggle("on",a.dataset.tab===t)});if(rf){clearInterval(rf);rf=null}load(t)}
function refresh(ms,cb){if(rf)clearInterval(rf);if(ms>0)rf=setInterval(cb,ms)}
function load(t){var m={dashboard:loD,servers:loS,relay:loRe,tracker:loTr,players:loP,compensations:loCm,exchange:loEx,lottery:loLo,online:loOn,audit:loAu,macros:loMa,scripts:loSc,logviewer:loLogViewer,cmd:loCmd,settings:loCfg};if(m[t])m[t]()}
/* ====== 仪表盘 ====== */
async function loD(){var s=await fj(A+"/status"),pc=await fj(A+"/compensations/count?status=pending");document.getElementById("main").innerHTML='<div class="sts"><div class="st" onclick="nav(\'servers\')"><div class="n">'+(s.group_count||0)+'</div><div class="l">群聊数量</div></div><div class="st" onclick="nav(\'servers\')"><div class="n">'+(s.server_count||0)+'</div><div class="l">服务器数量</div></div><div class="st" onclick="nav(\'players\')"><div class="n">'+(s.player_count||0)+'</div><div class="l">玩家总数</div></div><div class="st" onclick="nav(\'online\')"><div class="n">'+(s.online_count||0)+'</div><div class="l">当前在线</div></div><div class="st" onclick="nav(\'compensations\')"><div class="n">'+(pc.count||0)+'</div><div class="l">待处理补偿</div></div><div class="st" onclick="nav(\'settings\')"><div class="n">'+(s.admin_count||0)+'</div><div class="l">管理员</div></div><div class="st" onclick="nav(\'macros\')"><div class="n">'+(s.macro_count||0)+'</div><div class="l">宏命令</div></div><div class="st" onclick="nav(\'scripts\')"><div class="n">'+(s.script_count||0)+'</div><div class="l">脚本文件</div></div></div><div class="ct"><h3>全局状态</h3><table><tr><th>功能模块</th><th>运行状态</th><th>关键参数</th></tr><tr><td>群服互联</td><td><span class="t1 '+(s.relay_enabled?'t-on':'t-off')+'">'+(s.relay_enabled?'已开启':'已关闭')+'</span></td><td>'+s.relay_fmt+'</td></tr><tr><td>在线追踪</td><td><span class="t1 '+(s.tracker_enabled?'t-on':'t-off')+'">'+(s.tracker_enabled?'已开启':'已关闭')+'</span></td><td>轮询间隔 '+s.tracker_interval+'秒 / 踢出阈值 '+s.kick_threshold+'分钟</td></tr><tr><td>玩家数据库</td><td><span class="t1 '+(s.pdb_enabled?'t-on':'t-off')+'">'+(s.pdb_enabled?'已开启':'已关闭')+'</span></td><td>签到积分 '+s.checkin_pts+' / 补偿功能 '+(s.comp_enabled?'开启':'关闭')+'</td></tr><tr><td>速率限制</td><td><span class="t1 '+(s.rate_enabled?'t-on':'t-off')+'">'+(s.rate_enabled?'已开启':'已关闭')+'</span></td><td>基础 '+s.rate_base+'ms / 阈值 '+s.rate_threshold+'次</td></tr><tr><td>危险命令黑名单</td><td><span class="t1 '+(s.dangerous_count>0?'t-off':'t-on')+'">'+(s.dangerous_count>0?'已启用('+s.dangerous_count+'条)':'未设置')+'</span></td><td style="font-size:11px;color:var(--m)">'+(s.dangerous_list||[]).join(', ')||'-'+'</td></tr></table></div>'}
/* ====== Servers ====== */
async function loS(){var g=await fj(A+"/groups"),gns=await fj(A+"/group-names"),h='<div class="fb"><h3 style="margin:0">服务器管理</h3><button class="b1 bs" onclick="addSvr()">+ 添加</button><button class="b2 bsm" style="margin-left:8px" onclick="loTpls()">📋 模板管理</button></div>';for(var id in g){var s=g[id]||[],nm=gns[id]||'';h+='<div class="ct"><h3>群 '+id+(nm?' ('+nm+')':'')+'<span class="badge">'+s.length+'台</span><button class="b2 bsm" onclick="addSvrG(\''+id+'\')">+ 添加</button></h3>';s.forEach(function(sv,i){h+='<div style="background:var(--bg);border-radius:4px;padding:10px;margin-bottom:5px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px"><div><strong>'+(sv.server_name||sv.name||'未命名')+'</strong><span style="color:var(--m);margin-left:6px;font-size:10px">'+sv.rcon_host+':'+sv.rcon_port+'</span><span class="t1 '+(sv.relay_enabled?'t-on':'t-off')+'" title="群服互联">互联</span><span class="t1 '+(sv.query_enabled!==false?'t-on':'t-off')+'">query</span><span class="t1 '+(sv.web_management_enabled!==false?'t-on':'t-off')+'">web</span>'+(sv.vote_enabled?'<span class="t1 t-on">vote:'+sv.vote_threshold+'</span>':'')+'</div><div class="ac"><button class="b2 bsm" onclick="edSvr(\''+id+'\','+i+')">编辑</button><button class="bd bsm" onclick="rmSvr(\''+id+'\','+i+')">删除</button></div></div>'});h+='</div>'}if(!Object.keys(g).length)h+='<div class="emp">暂无群聊</div>';document.getElementById("main").innerHTML=h}
function addSvr(){svrModal()}
function addSvrG(gid){svrModal(gid)}
function svrModal(gid){var m='<div class="mbg" id="sv-m" onclick="if(event.target===this)this.remove()"><div class="mod"><h3>'+(gid?'添加服务器到群 '+gid:'添加服务器')+'</h3>';if(!gid){m+='<div class="fr"><div class="fg"><label>📋 从模板填充</label><select id="stpl" onchange="fillTpl(\'stpl\',\'sf\')"><option value="">-- 手动填写 --</option></select></div><div class="fg"><label>📋 从已有群聊选择</label><select id="stpl-grp" onchange="svrSelGrp(this.value)"><option value="">-- 选择群聊 --</option></select></div></div>'}m+='<div class="fg"><label title="QQ群号">群号 *</label><input id="sfg" value="'+(gid||'')+'" '+(gid?'readonly':'')+'></div>';if(gid){m+='<div class="fg"><label title="从模板填充">📋 从模板填充</label><select id="stpl" onchange="fillTpl(\'stpl\',\'sf\')"><option value="">-- 手动填写 --</option></select></div>'}m+='<div class="fr"><div class="fg"><label title="服务器显示名称">名称 *</label><input id="sfn" placeholder="生存一区"></div><div class="fg"><label title="RCON服务器地址">RCON地址 *</label><input id="sfh" placeholder="127.0.0.1"></div></div><div class="fr"><div class="fg"><label title="RCON端口号">RCON端口 *</label><input id="sfp" value="25575"></div><div class="fg"><label title="RCON连接密码">密码 *</label><input id="sfpw" type="password"></div><div class="fg"><label title="MC游戏端口">游戏端口</label><input id="sfgp" value="25565"></div></div><div class="fg"><label title="服务端日志路径(事件监听)">日志路径</label><input id="sflp" placeholder="D:/mc/logs/latest.log"><div style="font-size:10px;color:#e74c3c;margin-top:2px">⚠ 日志文件必须能被插件运行环境直接读取。Docker中MC在另一容器时需先配置卷挂载</div></div><div class="fg"><label title="允许使用命令的QQ号，逗号分隔">白名单</label><input id="sfw" placeholder="111,222"></div><div class="fg"><label title="公开可用的命令列表，逗号分隔">公开命令</label><input id="sfu" value="list,say"></div><div class="fr"><div class="fg"><label title="群服互联开关">群服互联</label><select id="sfrl"><option value="0">关</option><option value="1">开</option></select></div><div class="fg"><label title="允许查询此服务器状态">查询</label><select id="sfq"><option value="1">开</option><option value="0">关</option></select></div><div class="fg"><label title="允许此群在Web面板中管理">Web管理</label><select id="sfwm"><option value="1" selected>开</option><option value="0">关</option></select></div></div><div style="margin-top:10px;padding-top:10px;border-top:1px solid var(--b)"><h4 style="font-size:12px;color:var(--m);margin-bottom:8px">投票</h4><div class="fr"><div class="fg"><label title="允许群内发起投票">开关</label><select id="sfvt0"><option value="0">关</option><option value="1">开</option></select></div><div class="fg"><label title="投票所需赞同人数">阈值</label><input id="sfvt" value="3" type="number"></div><div class="fg"><label title="投票有效期(秒)">TTL</label><input id="sfvttl" value="60" type="number"></div></div><div class="fr"><div class="fg"><label title="超时最小赞同人数">最小赞同</label><input id="sfvma" value="1" type="number"></div><div class="fg"><label title="平票处理策略">平票</label><select id="sfvts"><option value="fail">失败</option><option value="admin">裁决</option></select></div><div class="fg"><label title="管理员裁决超时(秒)">裁决TTL</label><input id="sfatl" value="120" type="number"></div></div></div><div class="fr" style="margin-top:14px"><button class="b1 bs" onclick="doAddSvr()">保存</button><button class="b2 bs" onclick="document.getElementById(\'sv-m\').remove()">取消</button></div></div></div>';document.body.insertAdjacentHTML("beforeend",m);fj(A+"/server-templates").then(function(t){window._tpls=t;var s=document.getElementById("stpl");if(s){t.forEach(function(v){s.innerHTML+='<option value=\"'+v.name+'\">'+v.name+'</option>'})}});if(!gid){fj(A+"/config-servers").then(function(cs){var grps=cs&&cs.groups?cs.groups:[];var gns=cs&&cs.group_names?cs.group_names:{};var s=document.getElementById("stpl-grp");if(s){grps.forEach(function(g){var gn=gns[g]||'';s.innerHTML+='<option value=\"'+g+'\">'+(gn?g+' ('+gn+')':'群 '+g)+'</option>'})}})}}
async function doAddSvr(){var g=document.getElementById("sfg").value.trim();if(!g){toast("请输入群号",true);return}var b={group_id:g,name:document.getElementById("sfn").value.trim(),rcon_host:document.getElementById("sfh").value.trim(),rcon_port:document.getElementById("sfp").value.trim(),rcon_password:document.getElementById("sfpw").value.trim(),game_port:document.getElementById("sfgp").value.trim(),whitelist_qqs:document.getElementById("sfw").value.split(",").map(function(s){return s.trim()}).filter(Boolean),public_commands:document.getElementById("sfu").value.split(",").map(function(s){return s.trim()}).filter(Boolean),relay_enabled:document.getElementById("sfrl").value=="1",query_enabled:document.getElementById("sfq").value=="1",web_management_enabled:document.getElementById("sfwm").value=="1",vote_enabled:document.getElementById("sfvt0").value=="1",vote_threshold:parseInt(document.getElementById("sfvt").value)||3,vote_ttl:parseInt(document.getElementById("sfvttl").value)||60,vote_min_agree_on_timeout:parseInt(document.getElementById("sfvma").value)||1,vote_tie_strategy:document.getElementById("sfvts").value,admin_decide_ttl:parseInt(document.getElementById("sfatl").value)||120,log_path:document.getElementById("sflp").value.trim()};await pj(A+"/servers",b);document.getElementById("sv-m")?.remove();toast("已添加");loS()}
async function edSvr(gid,idx){var s=await fj(A+"/servers/"+gid+"/"+idx);var m='<div class="mbg" id="es-m" onclick="if(event.target===this)this.remove()"><div class="mod"><h3>编辑: '+(s.server_name||s.name)+'</h3><div class="fg"><label title="从模板填充">📋 从模板填充</label><select id="etpl" onchange="fillTpl(\'etpl\',\'ef\')"><option value="">-- 手动填写 --</option></select></div><div class="fr"><div class="fg"><label title="服务器显示名称">名称</label><input id="efn" value="'+(s.server_name||s.name||'')+'" title="修改服务器在面板中的显示名称，不影响RCON连接"></div><div class="fg"><label title="RCON服务器地址">RCON地址</label><input id="efh" value="'+(s.rcon_host||'')+'" title="修改MC服务器的RCON地址，如 127.0.0.1 或公网IP"></div></div><div class="fr"><div class="fg"><label title="RCON端口号">端口</label><input id="efp" value="'+(s.rcon_port||'')+'" title="修改RCON端口，默认25575，需与server.properties中一致"></div><div class="fg"><label title="RCON连接密码">密码</label><input id="efpw" value="'+(s.rcon_password||'')+'" title="修改RCON连接密码，需与server.properties中rcon.password一致"></div><div class="fg"><label title="MC游戏端口">游戏端口</label><input id="efgp" value="'+(s.game_port||'25565')+'" title="MC服务器游戏端口，默认25565，用于状态查询"></div></div><div class="fg"><label title="服务端日志路径(事件监听)">日志路径</label><input id="eflp" value="'+(s.log_path||'')+'" title="MC服务器latest.log的完整路径，用于日志事件监听"><div style="font-size:10px;color:#e74c3c;margin-top:2px">⚠ 日志文件必须能被插件运行环境直接读取。Docker中MC在另一容器时需先配置卷挂载</div></div><div class="fg"><label title="允许使用命令的QQ号，逗号分隔">白名单</label><input id="efw" value="'+(s.whitelist_qqs||[]).join(',')+'" title="允许直接执行RCON命令的QQ号，逗号分隔"></div><div class="fg"><label title="公开可用的命令列表，逗号分隔">公开命令</label><input id="efu" value="'+(s.public_commands||[]).join(',')+'" title="非白名单用户可执行的命令，逗号分隔，如 list,say"></div><div class="fr"><div class="fg"><label title="群服互联开关">群服互联</label><select id="efrl"><option value="1" '+(s.relay_enabled?'selected':'')+'>开</option><option value="0" '+(!s.relay_enabled?'selected':'')+'>关</option></select></div><div class="fg"><label title="允许查询此服务器状态">查询</label><select id="efq"><option value="1" '+(s.query_enabled!==false?'selected':'')+'>开</option><option value="0" '+(s.query_enabled===false?'selected':'')+'>关</option></select></div><div class="fg"><label title="共享到其他群">共享</label><select id="efsh"><option value="0">否</option><option value="1" '+(s.shared?'selected':'')+'>是</option></select></div><div class="fg"><label title="允许此群在Web面板中管理">Web管理</label><select id="efwm"><option value="1" '+(s.web_management_enabled!==false?'selected':'')+'>开</option><option value="0" '+(s.web_management_enabled===false?'selected':'')+'>关</option></select></div></div><div style="margin-top:10px;padding-top:10px;border-top:1px solid var(--b)"><h4 style="font-size:12px;color:var(--m);margin-bottom:8px">投票</h4><div class="fr"><div class="fg"><label title="允许群内发起投票">开关</label><select id="efvt0"><option value="1" '+(s.vote_enabled?'selected':'')+'>开</option><option value="0" '+(!s.vote_enabled?'selected':'')+'>关</option></select></div><div class="fg"><label title="投票所需赞同人数">阈值</label><input id="efvt" value="'+(s.vote_threshold||3)+'" type="number" title="投票通过所需最少赞同人数"></div><div class="fg"><label title="投票有效期(秒)">TTL</label><input id="efvttl" value="'+(s.vote_ttl||60)+'" type="number" title="投票超时时间(秒)"></div></div><div class="fr"><div class="fg"><label title="超时最小赞同人数">最小赞同</label><input id="efvma" value="'+(s.vote_min_agree_on_timeout||1)+'" type="number" title="投票超时所需最小赞同人数"></div><div class="fg"><label title="平票处理策略">平票</label><select id="efvts"><option value="fail" '+(s.vote_tie_strategy==='fail'?'selected':'')+'>失败</option><option value="admin" '+(s.vote_tie_strategy==='admin'?'selected':'')+'>裁决</option></select></div><div class="fg"><label title="管理员裁决超时(秒)">裁决TTL</label><input id="efatl" value="'+(s.admin_decide_ttl||120)+'" type="number" title="平票时管理员裁决超时(秒)"></div></div></div><div class="fr" style="margin-top:14px"><button class="b1 bs" onclick="doEdSvr(\''+gid+'\','+idx+')">保存</button><button class="b2 bs" onclick="document.getElementById(\'es-m\').remove()">取消</button></div></div></div>';document.body.insertAdjacentHTML("beforeend",m);fj(A+"/server-templates").then(function(t){window._tpls=t;var s=document.getElementById("etpl");if(s){t.forEach(function(v){s.innerHTML+='<option value=\"'+v.name+'\">'+v.name+'</option>'})}})}
async function doEdSvr(gid,idx){var b={name:document.getElementById("efn").value.trim(),rcon_host:document.getElementById("efh").value.trim(),rcon_port:document.getElementById("efp").value.trim(),rcon_password:document.getElementById("efpw").value.trim(),game_port:document.getElementById("efgp").value.trim(),whitelist_qqs:document.getElementById("efw").value.split(",").map(function(s){return s.trim()}).filter(Boolean),public_commands:document.getElementById("efu").value.split(",").map(function(s){return s.trim()}).filter(Boolean),relay_enabled:document.getElementById("efrl").value=="1",query_enabled:document.getElementById("efq").value=="1",shared:document.getElementById("efsh").value=="1",web_management_enabled:document.getElementById("efwm").value=="1",vote_enabled:document.getElementById("efvt0").value=="1",vote_threshold:parseInt(document.getElementById("efvt").value)||3,vote_ttl:parseInt(document.getElementById("efvttl").value)||60,vote_min_agree_on_timeout:parseInt(document.getElementById("efvma").value)||1,vote_tie_strategy:document.getElementById("efvts").value,admin_decide_ttl:parseInt(document.getElementById("efatl").value)||120,log_path:document.getElementById("eflp").value.trim()};await pjt(A+"/servers/"+gid+"/"+idx,b);document.getElementById("es-m")?.remove();toast("已更新");loS()}
async function rmSvr(gid,idx){if(!confirm("确定删除？"))return;await fetch(A+"/servers/"+gid+"/"+idx,{method:"DELETE"});toast("已删除");loS()}
function edGrpName(gid,old){var n=prompt("群 "+gid+" 的显示名称:",old||"");if(n!==null){var nn=n.trim()||"";pjt(A+"/group-names/"+gid,{name:nn}).then(function(){toast("已保存");loS()})}}
async function loTpls(){var t=await fj(A+"/server-templates");var cs=await fj(A+"/config-servers");var gns=await fj(A+"/group-names");var grps=cs&&cs.groups?cs.groups:[];window._gns=gns;var h='<div class="ct" style="margin-bottom:16px;padding:12px"><div class="fb" style="margin-bottom:10px"><h3 style="margin:0">🏷️ 群名称配置</h3></div><div style="font-size:11px;color:var(--m);margin-bottom:8px">为群号设置别名，方便各页面识别</div><div class="fr" style="align-items:flex-end"><div class="fg"><label>选择群聊</label><select id="tpl-gn-sel" onchange="tplGnSel(this.value)"><option value="">-- 选择群号 --</option>';grps.forEach(function(g){var nm=gns[g]||'';h+='<option value="'+g+'">'+g+(nm?' ('+nm+')':'')+'</option>'});h+='</select></div><div class="fg"><label>显示名称</label><input id="tpl-gn-inp" placeholder="输入名称后回车" onkeydown="if(event.key===\'Enter\')tplGnSave()" style="min-width:200px"></div><button class="b1 bsm" onclick="tplGnSave()">💾 保存</button>'+(grps.length?'<button class="b2 bsm" style="margin-left:4px" onclick="tplGnClear()">🧹 清除</button>':'')+'</div></div>';h+='<div class="fb"><h3 style="margin:0">📋 服务器配置模板</h3><button class="b1 bs" onclick="addTpl()">+ 添加模板</button><button class="b2 bsm" style="margin-left:8px" onclick="loS()">← 返回服务器管理</button></div>';t.forEach(function(v,i){h+='<div class="ct"><div style="display:flex;justify-content:space-between;align-items:center"><div><strong>'+v.name+'</strong><span style="color:var(--m);font-size:10px;margin-left:8px">'+v.rcon_host+':'+v.rcon_port+'</span><span class="t1 '+(v.query_enabled!==false?'t-on':'t-off')+'">query</span></div><div><button class="b2 bsm" onclick="edTpl('+i+')">编辑</button><button class="bd bsm" onclick="rmTpl(\''+v.name+'\')">删除</button></div></div></div>'});if(!t.length)h+='<div class="emp">暂无模板</div>';document.getElementById("main").innerHTML=h;window._tpls=t}
function tplGnSel(gid){if(!gid){document.getElementById("tpl-gn-inp").value="";return}var nm=(window._gns||{})[gid]||"";document.getElementById("tpl-gn-inp").value=nm}
async function tplGnSave(){var gid=document.getElementById("tpl-gn-sel").value;var inp=document.getElementById("tpl-gn-inp");if(!gid){toast("请先选择一个群号",true);return}var nm=inp.value.trim();if(nm)await pjt(A+"/group-names/"+gid,{name:nm});else await fetch(A+"/group-names/"+gid,{method:"DELETE"});window._gns=window._gns||{};window._gns[gid]=nm;toast(nm?"已设置":"已清除");loTpls()}
async function tplGnClear(){var gid=document.getElementById("tpl-gn-sel").value;if(!gid){toast("请先选择一个群号",true);return}await fetch(A+"/group-names/"+gid,{method:"DELETE"});window._gns=window._gns||{};window._gns[gid]="";toast("已清除");loTpls()}
function addTpl(){tplModal()}
async function tplModal(idx){var t=idx!==undefined?window._tpls[idx]:{};var cs=await fj(A+"/config-servers");var svrs=cs&&cs.servers?cs.servers:[];var grps=cs&&cs.groups?cs.groups:[];var gns=cs&&cs.group_names?cs.group_names:{};var m='<div class="mbg" id="tp-m" onclick="if(event.target===this)this.remove()"><div class="mod"><h3>'+(idx!==undefined?'编辑模板':'新建模板')+'</h3>';if(idx===undefined){m+='<div class="fr" style="margin-bottom:8px">';m+='<div class="fg"><label>📋 从已有服务器选择</label><select onchange="tpSelSrv(this.value)" id="tpsrv"><option value="">-- 选择服务器 --</option>';svrs.forEach(function(s){m+='<option value="'+s+'">'+s+'</option>'});m+='</select></div>';m+='<div class="fg"><label>📋 从已有群聊选择</label><select onchange="tpSelGrp(this.value)" id="tpgid"><option value="">-- 选择群聊 --</option>';grps.forEach(function(g){var gn=gns[g]||'';m+='<option value="'+g+'">'+(gn?g+' ('+gn+')':'群 '+g)+'</option>'});m+='</select></div></div>'}m+='<div class="fg"><label>模板名称</label><input id="tpn" value="'+(t.name||'')+'"></div><div class="fr"><div class="fg"><label>RCON地址</label><input id="tph" value="'+(t.rcon_host||'')+'"></div><div class="fg"><label>RCON端口</label><input id="tpp" value="'+(t.rcon_port||'25575')+'"></div></div><div class="fr"><div class="fg"><label>密码</label><input id="tppw" value="'+(t.rcon_password||'')+'"></div><div class="fg"><label>游戏端口</label><input id="tpgp" value="'+(t.game_port||'25565')+'"></div></div><div class="fg"><label>查询</label><select id="tpq"><option value="1" '+(t.query_enabled!==false?'selected':'')+'>开</option><option value="0" '+(t.query_enabled===false?'selected':'')+'>关</option></select></div><div style="margin-top:12px"><button class="b1 bs" onclick="saveTpl('+(idx!==undefined?idx:'-1')+')">保存</button><button class="b2 bs" onclick="document.getElementById(\'tp-m\').remove()">取消</button></div></div></div>';document.body.insertAdjacentHTML("beforeend",m);window._tpGnames=gns}
function tpSelSrv(v){document.getElementById("tpn").value=v;_tpSyncName()}
function tpSelGrp(v){_tpSyncName()}
function _tpSyncName(){var s=document.getElementById("tpsrv")?.value||'',g=document.getElementById("tpgid")?.value||'';if(s&&g){var gn=window._tpGnames||{};var gl=gn[g]?'('+gn[g]+')':'';document.getElementById("tpn").value=gl+'_'+s}else if(!s&&g){var gn=window._tpGnames||{};document.getElementById("tpn").value=gn[g]||g}}
async function saveTpl(idx){var b={name:document.getElementById("tpn").value.trim(),rcon_host:document.getElementById("tph").value.trim(),rcon_port:document.getElementById("tpp").value.trim(),rcon_password:document.getElementById("tppw").value.trim(),game_port:document.getElementById("tpgp").value.trim(),query_enabled:document.getElementById("tpq").value=="1"};if(!b.name){toast("请输入模板名称",true);return}if(idx>=0){var old=window._tpls[idx].name;await pjt(A+"/server-templates/"+old,b)}else{await pj(A+"/server-templates",b)}document.getElementById("tp-m")?.remove();toast("已保存");loTpls()}
function edTpl(idx){tplModal(idx)}
async function rmTpl(name){if(!confirm("删除模板 "+name+"?"))return;await fetch(A+"/server-templates/"+name,{method:"DELETE"});toast("已删除");loTpls()}
async function fillTpl(selId,pref){var v=document.getElementById(selId).value;if(!v)return;var t=window._tpls||await fj(A+"/server-templates");for(var i=0;i<t.length;i++){if(t[i].name===v){document.getElementById(pref+"h").value=t[i].rcon_host||'';document.getElementById(pref+"p").value=t[i].rcon_port||'25575';document.getElementById(pref+"pw").value=t[i].rcon_password||'';document.getElementById(pref+"gp").value=t[i].game_port||'25565';document.getElementById(pref+"q").value=t[i].query_enabled!==false?'1':'0';break}}}
function svrSelGrp(v){if(v)document.getElementById("sfg").value=v}
/* ====== 群服互联 ====== */
async function loRe(){var g=await fj(A+"/groups?filter_web_mgmt=1"),all=await fj(A+"/relay/all"),gc=await fj(A+"/config/relay");window._gc=gc;var allSrv=[],seen={};for(var gid in g){var srvs=g[gid]||[];for(var i=0;i<srvs.length;i++){var s=srvs[i];var sn=s.server_name||s.name||'';if(sn&&!seen[sn]){seen[sn]=true;allSrv.push(sn)}}}var h='<div class="ct"><h3>全局互联设置</h3><table><tr><th>群→服</th><th>服→群</th><th>服→群(日志)</th><th>必须 /msay</th><th>群→服格式</th><th>服→群格式</th><th>服→群日志格式</th></tr><tr><td><label class="tg" title="全局群聊→服务器消息转发"><input type="checkbox" '+(gc.relay_group_to_mc?'checked':'')+' onchange="relayGlobalSet(\'relay_group_to_mc\',this.checked)"><span class="sl"></span></label></td><td><label class="tg" title="全局服务器→群聊消息转发"><input type="checkbox" '+(gc.relay_mc_to_group?'checked':'')+' onchange="relayGlobalSet(\'relay_mc_to_group\',this.checked)"><span class="sl"></span></label></td><td><label class="tg" title="基于日志监听实现服→群转发（无需MC模组），延迟~0.5-1s"><input type="checkbox" '+(gc.relay_mc_to_group_log?'checked':'')+' onchange="relayGlobalSet(\'relay_mc_to_group_log\',this.checked)"><span class="sl"></span></label></td><td><label class="tg" title="必须 /msay 才允许转发"><input type="checkbox" '+(gc.relay_require_msay?'checked':'')+' onchange="relayGlobalSet(\'relay_require_msay\',this.checked)"><span class="sl"></span></label></td><td style="min-width:200px">'+fmtEditor('fmt_group',gc.relay_fmt_group||'[QQ] {name}: {msg}','','',true)+'</td><td style="min-width:200px">'+fmtEditor('fmt_mc',gc.relay_fmt_mc||'[MC] {player}: {msg}','','',true)+'</td><td style="min-width:200px">'+fmtEditor('fmt_mc_log',gc.relay_fmt_mc_log||'','','',true)+'</td></tr></table></div><div class="ct" style="margin:8px 0;padding:8px 10px"><h4 style="margin:0 0 6px;font-size:12px">🏷️ 日志转发类型前缀</h4><div style="display:flex;flex-wrap:wrap;gap:4px;align-items:center">'+(function(){var pfx=gc.log_type_prefixes||{};var types=[["chat","💬聊天"],["command","⌨️命令"],["player_death","💀死亡"],["player_join","🚪进入"],["player_leave","🚪离开"],["player_advancement","⭐成就"],["system","⚙️系统"],["other","📎其他"]];var s='';for(var i=0;i<types.length;i++){var tv=types[i][0],tn=types[i][1];var pv=pfx[tv]||'';s+='<span style="white-space:nowrap;font-size:11px">'+tn+'</span><input value="'+pv.replace(/"/g,"&quot;").replace(/\'/g,"&#39;")+'" onchange="relaySetPrefix(\''+tv+'\',this.value)" style="width:36px;font-size:11px;padding:1px 3px;margin-right:8px" title="'+tn+'前缀">'}return s})()+'</div><span style="font-size:9px;color:var(--m)">修改后即时生效。留空=不添加前缀，例如把「💀死亡」改成「☠️」使用自定义emoji</span></div><div class="ct" style="margin:8px 0;background:rgba(255,193,7,.06);border:1px dashed rgba(255,193,7,.25);padding:8px 12px;border-radius:4px;font-size:11px;line-height:1.6"><span style="color:var(--m)">⚠ 服→群转发需 MC 服务端安装配套模组或使用日志监听替代：</span><a href="https://github.com/rogergzl/astrbot_plugin_mrconop" target="_blank" style="color:var(--s);text-decoration:underline;margin-left:4px">📥 下载 MC 模组（待开发）</a><br><span style="color:var(--w);font-size:10px">✅ 替代方案：在上方全局设置中开启<span style="color:var(--a)">服→群(日志)</span>，并在群绑定中配置 <span style="color:var(--a)">日志类型</span> 即可实现服→群转发，延迟 ~0.5-1s</span><br><span style="color:var(--d);font-size:10px">⚠ 温馨提示：使用日志方式互联需要在目标群里先发任意一条消息，否则机器人无法获取群信息</span></div><div class="fb" style="margin:16px 0 8px"><h3 style="margin:0">群-服绑定</h3><button class="b1 bsm" onclick="relayAutoBind()">🔄 自动绑定所有</button></div>';var has=false;for(var gid in g){var entries=all[gid]||[],srvs=g[gid]||[],nm=gn(srvs),dnm=(nm?nm+' (':'')+'QQ:'+gid+(nm?')':'');if(!entries.length)entries=[{server_name:srvs[0]?.server_name||srvs[0]?.name||'',group_to_mc:false,mc_to_group:false,mode:'off'}];has=true;var mode=(entries[0]&&entries[0].mode)||'off';h+='<div class="rl-card"><span class="rl-grp">'+dnm+'</span><select style="width:100px;margin-right:8px" onchange="relaySetMode(\''+gid+'\',this.value)"><option value="off"'+(mode==='off'?' selected':'')+'>不互通</option><option value="global"'+(mode==='global'?' selected':'')+'>遵循全局</option><option value="custom"'+(mode==='custom'?' selected':'')+'>独立配置</option></select><button class="b1 bsm" style="font-size:11px" onclick="relayAddEntry(\''+gid+'\')" title="添加额外服务器绑定">+ 添加</button>';var isCustom=mode==='custom';for(var j=0;j<entries.length;j++){var e=entries[j]||{},esn=e.server_name||'';h+='<div class="rl-row"><span class="rl-arrow">→</span><select class="rl-sel" onchange="relaySetEntry(\''+gid+'\','+j+',\'server_name\',this.value)" title="选择目标服务器">';for(var k=0;k<allSrv.length;k++){h+='<option value="'+allSrv[k]+'"'+(allSrv[k]===esn?' selected':'')+'>'+allSrv[k]+'</option>'}h+='</select><span class="rl-lbl">群→服</span><label class="tg" title="群聊→服务器转发"><input type="checkbox" '+(e.group_to_mc===true?'checked':'')+' '+(isCustom?'':'disabled')+' onchange="relaySetEntry(\''+gid+'\','+j+',\'group_to_mc\',this.checked)"><span class="sl"></span></label><span class="rl-lbl">服→群</span><label class="tg" title="服务器→群聊转发"><input type="checkbox" '+(e.mc_to_group===true?'checked':'')+' '+(isCustom?'':'disabled')+' onchange="relaySetEntry(\''+gid+'\','+j+',\'mc_to_group\',this.checked)"><span class="sl"></span></label><span class="rl-lbl">服→群(日志)</span><label class="tg" title="基于日志监听实现服→群转发"><input type="checkbox" '+(e.m2g_log_enabled?'checked':'')+' '+(isCustom?'':'disabled')+' onchange="relaySetEntry(\''+gid+'\','+j+',\'m2g_log_enabled\',this.checked)"><span class="sl"></span></label><button class="b2 bsm" onclick="relaySetLogTypes(\''+gid+'\','+j+')" style="font-size:10px;padding:1px 6px" title="配置转发日志类型">📋类型</button><button class="b2 bsm" onclick="relaySetPrefixes(\''+gid+'\','+j+')" style="font-size:10px;padding:1px 6px" title="配置日志类型前缀">🏷️前缀</button><span class="rl-lbl">必须 /msay 才允许转发</span><label class="tg" title="必须 /msay 才允许转发"><input type="checkbox" '+(e.require_msay===true?'checked':'')+' '+(isCustom?'':'disabled')+' onchange="relaySetEntry(\''+gid+'\','+j+',\'require_msay\',this.checked)"><span class="sl"></span></label>';if(isCustom){var hasGfmt=e.format_group!==undefined,hasMfmt=e.format_mc!==undefined,hasLfmt=e.format_mc_log!==undefined;h+='<div class="fmt-row"><span class="fmt-title">群→服格式'+(hasGfmt?'':' <span style="color:var(--m);font-size:10px">(全局默认)</span>')+'</span>'+fmtEditor('format_group',e.format_group||gc.relay_fmt_group||'[QQ] {name}: {msg}',gid,j,true)+'</div><div class="fmt-row"><span class="fmt-title">服→群格式'+(hasMfmt?'':' <span style="color:var(--m);font-size:10px">(全局默认)</span>')+'</span>'+fmtEditor('format_mc',e.format_mc||gc.relay_fmt_mc||'[MC] {player}: {msg}',gid,j,true)+'</div><div class="fmt-row"><span class="fmt-title">服→群日志格式'+(hasLfmt?'':' <span style="color:var(--m);font-size:10px">(同服→群格式)</span>')+'</span>'+fmtEditor('format_mc_log',e.format_mc_log||gc.relay_fmt_mc||'[MC] {player}: {msg}',gid,j,true)+'</div>'};if(entries.length>1){h+='<button class="bd bsm" style="font-size:10px;padding:2px 6px" onclick="relayDelEntry(\''+gid+'\','+j+')" title="移除此绑定">✕</button>'}h+='</div>'}h+='</div>'}if(!has)h+='<div class="emp">暂无群聊</div>';document.getElementById("main").innerHTML=h}
async function relayGlobalSet(key,val){var b={};b[key]=typeof val==="boolean"?val:val;await pjt(A+"/config/relay",b);toast("已更新");loRe()}
async function relaySetMode(gid,mode){var entries=await fj(A+"/relay/"+gid);if(!entries.length)entries=[{server_name:"",group_to_mc:false,mc_to_group:false}];for(var i=0;i<entries.length;i++)entries[i].mode=mode;await pjt(A+"/relay/"+gid,entries);toast("已更新模式");loRe()}
async function relayAutoBind(){var g=await fj(A+"/groups?filter_web_mgmt=1"),all=await fj(A+"/relay/all");for(var id in g){var srvs=g[id]||[];if(srvs.length>0){var sn=srvs[0].server_name||srvs[0].name||'';if(sn){var exist=all[id]||[];if(!exist.some(function(e){return e.server_name===sn})){exist.push({server_name:sn,group_to_mc:false,mc_to_group:false,mode:'off'});await pjt(A+"/relay/"+id,exist)}}}}toast("已自动绑定");loRe()}
async function relayAddEntry(gid){var sn=prompt("输入要绑定的服务器名称");if(!sn)return;await pj(A+"/relay/"+gid,{server_name:sn.trim(),group_to_mc:false,mc_to_group:false,mode:'custom'});toast("已添加");loRe()}
async function relayDelEntry(gid,idx){if(!confirm("确定删除此绑定？"))return;var entries=await fj(A+"/relay/"+gid);if(idx<entries.length){entries.splice(idx,1);await pjt(A+"/relay/"+gid,entries);toast("已删除");loRe()}}
async function relaySetEntry(gid,idx,key,val){var entries=await fj(A+"/relay/"+gid);if(idx<entries.length){entries[idx][key]=typeof val==="boolean"?val:val;await pjt(A+"/relay/"+gid,entries);toast("已更新")}}
async function relaySetSrv(gid,name){await pjt(A+"/relay/"+gid,{server_name:name});toast("服务器已更新")}
async function relayReset(gid){await fetch(A+"/relay/"+gid,{method:"DELETE"});toast("已重置");loRe()}
var LOG_TYPE_MAP=[["chat","💬聊天"],["command","⌨️命令"],["player_death","💀死亡"],["player_join,player_leave","🚪进出"],["player_advancement","⭐成就"],["system","⚙️系统"],["other","📎其他"]];async function relaySetPrefix(type,val){var pf=window._gc.log_type_prefixes||{};pf[type]=val;await relayGlobalSet('log_type_prefixes',pf)}async function relaySetLogTypes(gid,idx){var entries=await fj(A+"/relay/"+gid);if(idx>=entries.length)return;var entry=entries[idx];var curTypes=entry.log_types||[];var h='<div class="mbg" id="rlt-m" onclick="if(event.target===this)this.remove()"><div class="mod"><h3>日志转发类型 - '+(entry.server_name||'服务器')+'</h3><p style="font-size:11px;color:var(--m);margin-bottom:10px">选择需要通过日志监听转发到群聊的事件类型</p>';for(var i=0;i<LOG_TYPE_MAP.length;i++){var tv=LOG_TYPE_MAP[i][0],tn=LOG_TYPE_MAP[i][1];var checked=curTypes.indexOf(tv)>=0;h+='<label style="display:inline-flex;align-items:center;gap:4px;margin:4px 12px 4px 0;cursor:pointer;font-size:13px"><input type="checkbox" value="'+tv+'" '+(checked?'checked':'')+' onchange="var cb=this;var t=[];cb.parentElement.parentElement.querySelectorAll(\'input[type=checkbox]:checked\').forEach(function(c){t.push(c.value)});relaySetEntry(\''+gid+'\','+idx+',\'log_types\',t)" style="cursor:pointer"> '+tn+'</label>'}h+='<div style="margin-top:14px"><button class="b2 bs" onclick="document.getElementById(\'rlt-m\').remove()">关闭</button><span style="font-size:10px;color:var(--m);margin-left:8px">勾选后即时生效，无需保存</span><br><span style="font-size:9px;color:var(--d)">⚠ 使用日志方式互联需要在群里先发任意一条消息</span></div></div></div>';document.body.insertAdjacentHTML("beforeend",h)}async function relaySetPrefixes(gid,idx){var entries=await fj(A+"/relay/"+gid);if(idx>=entries.length)return;var entry=entries[idx];var curPfx=entry.log_type_prefixes||{};var types=[["chat","💬聊天"],["command","⌨️命令"],["player_death","💀死亡"],["player_join","🚪进入"],["player_leave","🚪离开"],["player_advancement","⭐成就"],["system","⚙️系统"],["other","📎其他"]];var h='<div class="mbg" id="rltp-m" onclick="if(event.target===this)this.remove()"><div class="mod"><h3>日志类型前缀 - '+(entry.server_name||'服务器')+'</h3><p style="font-size:11px;color:var(--m);margin-bottom:10px">自定义每种日志类型转发到该群时的前缀。留空=使用全局设置</p>';for(var i=0;i<types.length;i++){var tv=types[i][0],tn=types[i][1];var pv=curPfx[tv]||'';h+='<div style="display:flex;align-items:center;gap:8px;margin:4px 0"><span style="width:80px;font-size:12px">'+tn+'</span><input value="'+pv.replace(/"/g,"&quot;").replace(/\'/g,"&#39;")+'" onchange="var inp=this;var np={};inp.parentElement.parentElement.querySelectorAll(\'input\').forEach(function(el){np[el.dataset.type]=el.value});relaySetEntry(\''+gid+'\','+idx+',\'log_type_prefixes\',np)" data-type="'+tv+'" style="width:50px;font-size:12px;padding:2px 4px" placeholder="全局"></div>'}h+='<div style="margin-top:14px"><button class="b2 bs" onclick="document.getElementById(\'rltp-m\').remove()">关闭</button><span style="font-size:10px;color:var(--m);margin-left:8px">修改后即时生效。留空=使用全局前缀</span></div></div></div>';document.body.insertAdjacentHTML("beforeend",h)}/* 格式编辑器 */
function parseFmt(f){var r=[],re=/\{[a-z_]+\}/g,l=0,m;while((m=re.exec(f))!==null){if(m.index>l)r.push({t:'tx',v:f.slice(l,m.index)});r.push({t:'ph',v:m[0]});l=m.index+m[0].length}if(l<f.length)r.push({t:'tx',v:f.slice(l)});return r}
function fmtEditor(k,val,gid,j,custom){var gc=window._gc||{},p=parseFmt(val),cs='';for(var i=0;i<p.length;i++){var t=p[i].t==='ph'?'ph':'tx',lbl=p[i].v;if(t==='ph'){var ph={'{name}':'昵称','{msg}':'消息','{server}':'服务器','{player}':'MC玩家','{group}':'群名'}[lbl]||lbl;cs+='<span class="fmt-chip fc-ph" onclick="fmtChipRm(this)" title="占位符: '+lbl+'">'+lbl+'</span>'}else{cs+='<span class="fmt-chip fc-tx" onclick="fmtChipRm(this)" title="点击移除">'+lbl.replace(/</g,'&lt;')+'</span>'}}var ed='<div class="fmt-ed" data-k="'+k+'" data-g="'+(gid||'')+'" data-j="'+(j||0)+'" data-c="'+(custom?'1':'0')+'">'+cs;if(custom){var isGfmt=k==='fmt_group'||k==='format_group';ed+='<span class="fmt-add"><select onchange="fmtChipTmpl(this)" style="font-size:10px;padding:1px 4px;border:1px dashed var(--b);background:transparent;color:var(--m);border-radius:3px;cursor:pointer" title="选择预设模板"><option value="">📋 模板</option>'+(isGfmt?'<option value="'+gc.relay_fmt_group+'">全局默认: '+(gc.relay_fmt_group||'[QQ] {name}: {msg}')+'</option><option value="{name}: {msg}">昵称: 消息 （例: 小明: 大家好）</option><option value="[{server}] {name}: {msg}">[服务器] 昵称: 消息 （例: [生存服] 小明: 大家好）</option><option value="{msg}">仅消息内容 （例: 大家好）</option><option value="{name} 说: {msg}">昵称 说: 消息 （例: 小明 说: 大家好）</option>':'<option value="'+gc.relay_fmt_mc+'">全局默认: '+(gc.relay_fmt_mc||'[MC] {player}: {msg}')+'</option><option value="{player}: {msg}">玩家: 消息 （例: Steve: 大家好）</option><option value="[{server}] {player}: {msg}">[服务器] 玩家: 消息 （例: [生存服] Steve: 大家好）</option><option value="{msg}">仅消息内容 （例: 大家好）</option><option value="{player} 说: {msg}">玩家 说: 消息 （例: Steve 说: 大家好）</option>')+'</select>';ed+='<select onchange="fmtChipAdd(this)" style="font-size:10px;padding:1px 4px;border:1px dashed var(--b);background:transparent;color:var(--m);border-radius:3px;cursor:pointer"><option value="">+ 添加</option><option value="_txt">✏ 自定义文字</option><optgroup label="占位符（中文显示，内部英文）"><option value="{name}">昵称 {name}</option><option value="{msg}">消息内容 {msg}</option><option value="{server}">服务器名 {server}</option><option value="{player}">MC玩家 {player}</option><option value="{group}">群名 {group}</option></optgroup></select></span>'}ed+='</div>';return ed}
async function fmtChipTmpl(sel){var v=sel.value;if(!v){sel.selectedIndex=0;return}sel.selectedIndex=0;var ed=sel.closest('.fmt-ed'),k=ed.dataset.k,g=ed.dataset.g,j=parseInt(ed.dataset.j)||0;if(g)await relaySetEntry(g,j,k,v);else await relayGlobalSet('relay_'+k,v);loRe()}
async function fmtChipAdd(sel){var v=sel.value;if(!v){sel.selectedIndex=0;return}sel.selectedIndex=0;var ed=sel.closest('.fmt-ed'),k=ed.dataset.k,g=ed.dataset.g,j=parseInt(ed.dataset.j)||0;if(v==='_txt'){v=prompt('输入自定义文字');if(!v)return}var chips=Array.from(ed.querySelectorAll('.fmt-chip')),nv=chips.map(function(c){return c.textContent}).join('')+v;if(g)await relaySetEntry(g,j,k,nv);else await relayGlobalSet('relay_'+k,nv);loRe()}
async function fmtChipRm(el){var ed=el.closest('.fmt-ed'),k=ed.dataset.k,g=ed.dataset.g,j=parseInt(ed.dataset.j)||0,chips=Array.from(ed.querySelectorAll('.fmt-chip')),idx=chips.indexOf(el),nv='';for(var i=0;i<chips.length;i++)if(i!==idx)nv+=chips[i].textContent;if(g)await relaySetEntry(g,j,k,nv);else await relayGlobalSet('relay_'+k,nv);loRe()}
/* ====== 在线追踪 ====== */
async function loTr(){var g=await fj(A+"/groups?filter_web_mgmt=1"),all=await fj(A+"/tracker/all"),gc=await fj(A+"/config/tracker"),h='<div style="margin-bottom:10px;font-size:11px;color:var(--m);padding:6px 10px;background:var(--bg2);border-radius:6px">💡 <b>封禁命令占位符</b>: {player}=玩家名 | {minutes}=封禁时长(纯数字分钟) | {reason}=踢出原因 &nbsp; 例: tempban {player} {minutes}m {reason}</div><div class="ct"><h3>全局追踪设置</h3><table><tr><th>监控</th><th>提醒</th><th>提醒节点(分钟)</th><th>游戏内提醒</th><th>自动踢出</th><th>踢出阈值</th><th>封禁时长</th><th>封禁命令</th><th>踢出原因</th><th>时长模式</th><th>提醒@模式</th><th>提醒@格式</th><th>单次记录时长</th></tr><tr><td><label class="tg"><input type="checkbox" '+(gc.tracker_enabled?'checked':'')+' onchange="tkGlobalSet(\'tracker_enabled\',this.checked)"><span class="sl"></span></label></td><td><label class="tg"><input type="checkbox" '+(gc.tracker_notify?'checked':'')+' onchange="tkGlobalSet(\'tracker_notify\',this.checked)"><span class="sl"></span></label></td><td><input style="width:110px" value="'+(gc.tracker_notify_intervals||[]).join(',')+'" onchange="tkGlobalSet(\'tracker_notify_intervals\',this.value)"></td><td><label class="tg"><input type="checkbox" '+(gc.tracker_notify_game?'checked':'')+' onchange="tkGlobalSet(\'tracker_notify_game\',this.checked)"><span class="sl"></span></label></td><td><label class="tg"><input type="checkbox" '+(gc.tracker_kick_enabled?'checked':'')+' onchange="tkGlobalSet(\'tracker_kick_enabled\',this.checked)"><span class="sl"></span></label></td><td><input style="width:80px" value="'+gc.tracker_kick_threshold+'" onchange="tkGlobalSet(\'tracker_kick_threshold\',this.value)"></td><td><input style="width:70px" value="'+gc.tracker_ban_minutes+'" onchange="tkGlobalSet(\'tracker_ban_minutes\',this.value)"></td><td><input style="width:200px" value="'+gc.tracker_ban_cmd+'" onchange="tkGlobalSet(\'tracker_ban_cmd\',this.value)" title="{player}=玩家名 | {minutes}=封禁时长(分钟) | {reason}=踢出原因" placeholder="tempban {player} {minutes}m {reason}"></td><td><input style="width:150px" value="'+(gc.tracker_kick_reason||'§6{player}§r, §a你已在线§e{hours}§a小时§r, §c请休息§d{minutes}§c分钟吧§r')+'" onchange="tkGlobalSet(\'tracker_kick_reason\',this.value)" title="{player}=玩家名 | {hours}=已在线整小时 | {minutes}=封禁时长(分钟)" placeholder="§6{player}§r, §a已在线§e{hours}§a小时§r, §c请休息§d{minutes}§c分钟吧§r"></td><td><select onchange="tkGlobalSet(\'tracker_duration_mode\',this.value)" style="width:80px"><option value="session" '+(gc.tracker_duration_mode!=="cumulative"?'selected':'')+'>单次</option><option value="cumulative" '+(gc.tracker_duration_mode==="cumulative"?'selected':'')+'>累计</option></select></td><td><select onchange="tkGlobalSet(\'tracker_mention_mode\',this.value)" style="width:80px"><option value="player" '+(gc.tracker_mention_mode==="player"?"selected":"")+'>@玩家</option><option value="text" '+(gc.tracker_mention_mode==="text"?"selected":"")+'>纯文本</option><option value="admin" '+(gc.tracker_mention_mode==="admin"?"selected":"")+'>@管理员</option><option value="custom" '+(gc.tracker_mention_mode==="custom"?"selected":"")+'>自定义</option></select></td><td><input style="width:130px" value="'+gc.tracker_mention_format+'" onchange="tkGlobalSet(\'tracker_mention_format\',this.value)" placeholder="@{qq} {player}..."></td><td><input style="width:60px" value="'+(gc.ranking_reset_hours||24)+'" onchange="tkGlobalSet(\'ranking_reset_hours\',this.value)" title="0=永久保留，设置后仅统计最近N小时数据"></td></tr></table></div>';for(var id in g){var c=all[id]||{},srvs=g[id]||[],nm=gn(srvs),ov=Object.keys(c).length>0;h+='<div class="ct"><h3>'+(nm||('群 '+id))+'<span class="badge">'+(c.use_global?'使用全局':(ov?'已覆盖':'继承全局'))+'</span></h3><table><tr><th>提醒开关</th><th>提醒节点</th><th>游戏内提醒</th><th>踢出开关</th><th>踢出阈值</th><th>封禁时长</th><th>封禁命令</th><th>踢出原因</th><th>时长模式</th><th>使用全局</th><th>提醒@模式</th><th>提醒@格式</th><th>操作</th></tr><tr><td><label class="tg"><input type="checkbox" '+(c.notify_enabled?'checked':'')+' onchange="tkSet(\''+id+'\',\'notify_enabled\',this.checked)"><span class="sl"></span></label></td><td><input style="width:110px" value="'+(c.notify_intervals||gc.tracker_notify_intervals||'')+'" onchange="tkSet(\''+id+'\',\'notify_intervals\',this.value)"></td><td><label class="tg"><input type="checkbox" '+(c.notify_in_game?'checked':'')+' onchange="tkSet(\''+id+'\',\'notify_in_game\',this.checked)"><span class="sl"></span></label></td><td><label class="tg"><input type="checkbox" '+(c.kick_enabled?'checked':'')+' onchange="tkSet(\''+id+'\',\'kick_enabled\',this.checked)"><span class="sl"></span></label></td><td><input style="width:80px" value="'+(c.kick_threshold||gc.tracker_kick_threshold||'')+'" onchange="tkSet(\''+id+'\',\'kick_threshold\',this.value)"></td><td><input style="width:70px" value="'+(c.ban_minutes!==undefined?c.ban_minutes:gc.tracker_ban_minutes)+'" onchange="tkSet(\''+id+'\',\'ban_minutes\',this.value)"></td><td><input style="width:200px" value="'+(c.ban_cmd||gc.tracker_ban_cmd)+'" onchange="tkSet(\''+id+'\',\'ban_cmd\',this.value)" title="{player}=玩家名 | {minutes}=封禁时长(分钟) | {reason}=踢出原因" placeholder="tempban {player} {minutes}m {reason}"></td><td><input style="width:150px" value="'+(c.kick_reason||gc.tracker_kick_reason||'§6{player}§r, §a你已在线§e{hours}§a小时§r, §c请休息§d{minutes}§c分钟吧§r')+'" onchange="tkSet(\''+id+'\',\'kick_reason\',this.value)" title="{player}=玩家名 | {hours}=已在线整小时 | {minutes}=封禁时长(分钟)" placeholder="§6{player}§r, §a已在线§e{hours}§a小时§r, §c请休息§d{minutes}§c分钟吧§r"></td><td><select onchange="tkSet(\''+id+'\',\'duration_mode\',this.value)" style="width:80px"><option value="session" '+(c.duration_mode!=="cumulative"?'selected':'')+'>单次</option><option value="cumulative" '+(c.duration_mode==="cumulative"?'selected':'')+'>累计</option></select></td><td><label class="tg"><input type="checkbox" '+(c.use_global===true?'checked':'')+' onchange="tkSet(\''+id+'\',\'use_global\',this.checked)"><span class="sl"></span></label></td><td><select onchange="tkSet(\''+id+'\',\'mention_mode\',this.value)" style="width:80px"><option value="player" '+((c.mention_mode||gc.tracker_mention_mode||"player")==="player"?"selected":"")+'>@玩家</option><option value="text" '+((c.mention_mode||gc.tracker_mention_mode||"player")==="text"?"selected":"")+'>纯文本</option><option value="admin" '+((c.mention_mode||gc.tracker_mention_mode||"player")==="admin"?"selected":"")+'>@管理员</option><option value="custom" '+((c.mention_mode||gc.tracker_mention_mode||"player")==="custom"?"selected":"")+'>自定义</option></select></td><td><input style="width:130px" value="'+(c.mention_format||gc.tracker_mention_format||"")+'" onchange="tkSet(\''+id+'\',\'mention_format\',this.value)" placeholder="@{qq} {player}..."></td><td>'+(ov?'<button class="bd bsm" onclick="tkRs(\''+id+'\')">重置为全局</button>':'<span style="color:#555;font-size:10px">-</span>')+'</td></tr></table></div>'}if(!Object.keys(g).length)h+='<div class="emp">暂无群聊数据</div>';document.getElementById("main").innerHTML=h}
async function tkSet(gid,key,val){var b={};if(key==="notify_intervals"){try{b[key]=val.split(",").map(function(s){return parseInt(s.trim())}).filter(function(n){return!isNaN(n)})}catch(e){return}}else if(typeof val==="boolean")b[key]=val;else if(key==="duration_mode"||key==="mention_mode"||key==="mention_format"||key==="ban_cmd"||key==="kick_reason")b[key]=String(val);else{var n=parseInt(val);if(!isNaN(n))b[key]=n}await pjt(A+"/tracker/"+gid,b);toast("已更新")}
async function tkGlobalSet(key,val){var b={};if(key==="tracker_notify_intervals"){try{b[key]=val.split(",").map(function(s){return parseInt(s.trim())}).filter(function(n){return!isNaN(n)})}catch(e){return}}else if(typeof val==="boolean")b[key]=val;else if(key==="tracker_duration_mode"||key==="tracker_mention_mode"||key==="tracker_mention_format"||key==="tracker_ban_cmd"||key==="tracker_kick_reason")b[key]=String(val);else{var n=parseInt(val);if(!isNaN(n))b[key]=n}await pjt(A+"/config/tracker",b);toast("已更新全局追踪设置")}
async function tkRs(gid){await fetch(A+"/tracker/"+gid,{method:"DELETE"});toast("已重置");loTr()}
/* ====== 玩家管理 (可编辑) ====== */
async function loP(sq){var u=A+"/players";if(sq)u+="?search="+encodeURIComponent(sq);var p=await fj(u);var h='<div class="fb" style="margin-bottom:12px"><h3 style="margin:0">玩家管理 ('+(p?p.length:0)+'人)</h3><div class="if"><input placeholder="搜索 QQ号/MC ID..." style="width:220px" onkeyup="if(event.key===\'Enter\')loP(this.value)"><button class="b1 bsm" onclick="addPlayer()">+ 添加玩家</button><button class="bg bsm" onclick="importOnline()">从在线导入</button></div></div>';if(!p||!p.length){h+='<div class="emp">暂无玩家数据</div>';document.getElementById("main").innerHTML=h;return}h+='<div class="ct"><table><tr><th>QQ号</th><th>MC ID</th><th>积分</th><th>连续签到</th><th>VIP</th><th>最后签到</th><th>总在线时长</th><th>注册时间</th><th>操作</th></tr>';for(var i=0;i<p.length;i++){var r=p[i],dur=r.total_online_min?Math.floor(r.total_online_min/60)+"小时"+Math.floor(r.total_online_min%60)+"分钟":"-",ct=r.created_at?new Date(r.created_at*1000).toLocaleDateString("zh-CN"):"-";h+='<tr><td>'+r.qq_id+'</td><td><strong>'+(r.mc_id||"未绑定")+'</strong></td><td>'+r.points+'</td><td>'+(r.checkin_streak||0)+'天</td><td>'+(r.vip_level||0)+'</td><td>'+(r.last_checkin_date||"-")+'</td><td>'+dur+'</td><td>'+ct+'</td><td><div class="ac"><button class="bp bsm" onclick="edPlayer(\''+r.qq_id+'\')">编辑</button><button class="bg bsm" onclick="edPlayerCmd(\''+r.qq_id+'\',\''+(r.mc_id||'').replace(/'/g,"\\'")+'\')">命令</button><button class="bd bsm" onclick="rmPlayer(\''+r.qq_id+'\')">删除</button></div></td></tr>'}h+='</table></div>';document.getElementById("main").innerHTML=h}
function edPlayer(qq){var mc="",pts=0,strk=0,vip=0;var rows=document.querySelectorAll("tr");for(var i=0;i<rows.length;i++){var cells=rows[i].querySelectorAll("td");if(cells.length>=9&&cells[0].textContent.trim()===qq){mc=cells[1].textContent.trim();pts=parseInt(cells[2].textContent)||0;strk=parseInt(cells[3].textContent)||0;vip=parseInt(cells[4].textContent)||0;break}}var m='<div class="mbg" id="ep-m" onclick="if(event.target===this)this.remove()"><div class="mod"><h3>编辑玩家: '+qq+'</h3><div class="fr"><div class="fg"><label>QQ号</label><input id="ep-qq" value="'+qq+'" title="修改后将更换绑定的QQ号"></div><div class="fg"><label>MC ID（游戏ID）</label><input id="ep-mc" value="'+(mc==='未绑定'?'':mc)+'" title="修改绑定的MC游戏ID"></div></div><div class="fr"><div class="fg"><label>积分</label><input id="ep-pts" type="number" value="'+pts+'"></div><div class="fg"><label>连续签到天数</label><input id="ep-strk" type="number" value="'+strk+'"></div></div><div class="fr"><div class="fg"><label>VIP等级</label><input id="ep-vip" type="number" value="'+vip+'" min="0" max="3" title="0=普通玩家 1-3=VIP等级"></div></div><div class="fr" style="margin-top:14px"><button class="b1 bs" onclick="doEdPlayer(\''+qq+'\')">保存修改</button><button class="b2 bs" onclick="document.getElementById(\'ep-m\').remove()">取消</button></div></div></div>';document.body.insertAdjacentHTML("beforeend",m)}
async function doEdPlayer(qq){var nqq=document.getElementById("ep-qq").value.trim(),b={mc_id:document.getElementById("ep-mc").value.trim(),points:parseInt(document.getElementById("ep-pts").value)||0,checkin_streak:parseInt(document.getElementById("ep-strk").value)||0,vip_level:Math.min(Math.max(parseInt(document.getElementById("ep-vip").value)||0,0),3)};if(nqq&&nqq!==qq)b.new_qq_id=nqq;await pjt(A+"/players/"+qq,b);document.getElementById("ep-m")?.remove();toast("玩家信息已更新");loP()}
async function rmPlayer(qq){if(!confirm("确定要删除玩家 "+qq+" 吗？此操作不可撤销。"))return;await fetch(A+"/players/"+qq,{method:"DELETE"});toast("玩家已删除");loP()}
function addPlayer(){document.body.insertAdjacentHTML("beforeend",'<div class="mbg" id="ap-m" onclick="if(event.target===this)this.remove()"><div class="mod"><h3>添加玩家</h3><div class="fg"><label>QQ号 *</label><input id="ap-qq" placeholder="玩家QQ号"></div><div class="fg"><label>MC ID</label><input id="ap-mc" placeholder="玩家MC ID(可选)"></div><div class="fg"><label>初始积分</label><input id="ap-pts" type="number" value="50"></div><div class="fr" style="margin-top:14px"><button class="b1 bs" onclick="doAddPlayer()">添加</button><button class="b2 bs" onclick="document.getElementById(\'ap-m\').remove()">取消</button></div></div></div>')}
async function doAddPlayer(){var qq=document.getElementById("ap-qq").value.trim();if(!qq){toast("请输入QQ号",true);return}var b={qq_id:qq,mc_id:document.getElementById("ap-mc").value.trim(),points:parseInt(document.getElementById("ap-pts").value)||50};await pj(A+"/players",b);document.getElementById("ap-m")?.remove();toast("玩家已添加");loP()}
function importOnline(){document.getElementById("main").innerHTML='<div class="ct"><h3>正在扫描在线玩家...</h3><p style="color:var(--m)">正在从在线缓存中导入新玩家...</p></div>';fetch(A+"/players/import_online",{method:"POST"}).then(function(r){return r.json()}).then(function(d){var total=d.total_online||d.imported||0;if(d.imported>0)toast("已导入 "+d.imported+" 名新玩家（共扫描 "+total+" 人在线）");else toast("未有新玩家可导入（当前"+total+"人在线，均已存在）");loP()}).catch(function(e){toast("导入失败: "+e.message,true);loP()})}
/* ====== 抽奖管理 ====== */
var glo="";
async function loLo(){var g=await fj(A+"/groups?filter_web_mgmt=1");var gOpts='<option value="">选择群聊...</option>';for(var id in g){var nm=gn(g[id]);gOpts+='<option value="'+id+'" '+(id===glo?'selected':'')+'>'+(nm||'群 '+id)+'</option>'}var h='<div class="ct"><h3>🎰 抽奖管理</h3><div class="fb"><select onchange="glo=this.value;loLo()" style="width:200px">'+gOpts+'</select><button class="b1 bsm" onclick="showLoModal()" style="margin-left:8px">➕ 添加奖品</button></div>';if(glo){var items=await fj(A+"/lottery/"+glo);if(!items||!items.length){h+='<div class="emp">该群暂无奖品配置</div>'}else{h+='<table style="margin-top:12px"><tr><th>编号</th><th>名称</th><th>描述</th><th>概率</th><th>数量</th><th>消耗积分</th><th>RCON命令</th><th>状态</th><th>操作</th></tr>';for(var i=0;i<items.length;i++){var it=items[i];h+='<tr><td>'+it.id+'</td><td>'+it.name+'</td><td>'+(it.description||'-')+'</td><td>'+Math.round(it.probability*100)+'%</td><td>'+it.count+'</td><td>'+it.cost_points+'</td><td><code style="font-size:10px">'+it.rcon_cmd+'</code></td><td>'+(it.enabled?'<span style="color:var(--s)">启用</span>':'<span style="color:var(--d)">关闭</span>')+'</td><td><button class="bw bsm" onclick="showLoModal('+it.id+')">编辑</button><button class="bd bsm" onclick="delLo('+it.id+')">删除</button></td></tr>'}h+='</table>'}}else{h+='<div class="emp">请先选择一个群聊</div>'}h+='</div>';document.getElementById("main").innerHTML=h}
async function showLoModal(pid){var g=await fj(A+"/groups?filter_web_mgmt=1");var gOpts='<option value="">选择群聊...</option>';for(var id in g){var nm=gn(g[id]);gOpts+='<option value="'+id+'" '+(id===glo?'selected':'')+'>'+(nm||'群 '+id)+'</option>'}var it={name:"",description:"",probability:0.1,count:1,cost_points:10,rcon_cmd:"",enabled:1};var isEdit=false;if(pid){isEdit=true;var items=await fj(A+"/lottery/"+glo);for(var i=0;i<items.length;i++){if(items[i].id===pid){it=items[i];break}}}var h='<div class="mbg" id="lo-modal" onclick="if(event.target===this)this.remove()"><div class="mod"><h3>'+(isEdit?'编辑':'添加')+'奖品</h3><div class="fg"><label>所属群聊</label><select id="lo-gid" '+(isEdit?'disabled':'')+'>'+gOpts+'</select></div><div class="fg"><label>名称</label><input id="lo-name" value="'+it.name+'"></div><div class="fg"><label>描述</label><input id="lo-desc" value="'+(it.description||'')+'"></div><div class="fr"><div class="fg"><label>概率 (0~1)</label><input type="number" id="lo-prob" value="'+it.probability+'" step="0.01" min="0" max="1"></div><div class="fg"><label>每次数量</label><input type="number" id="lo-count" value="'+it.count+'"></div></div><div class="fg"><label>每次消耗积分</label><input type="number" id="lo-cost" value="'+it.cost_points+'"></div><div class="fg"><label>RCON命令 ({player}=玩家MC ID)</label><input id="lo-cmd" value="'+(it.rcon_cmd||'')+'"></div><div class="fg"><label>启用</label><select id="lo-enabled"><option value="1" '+(it.enabled?'selected':'')+'>是</option><option value="0" '+(!it.enabled?'selected':'')+'>否</option></select></div><div style="margin-top:12px"><button class="b1 bs" onclick="saveLo('+(isEdit?pid:0)+')">保存</button><button class="b2 bs" onclick="document.getElementById(\'lo-modal\').remove()" style="margin-left:8px">取消</button></div></div></div>';document.body.insertAdjacentHTML("beforeend",h)}
async function saveLo(pid){var sgid=glo;if(pid===0)sgid=document.getElementById("lo-gid").value;var d={name:document.getElementById("lo-name").value,description:document.getElementById("lo-desc").value,probability:parseFloat(document.getElementById("lo-prob").value)||0.1,count:parseInt(document.getElementById("lo-count").value)||1,cost_points:parseInt(document.getElementById("lo-cost").value)||10,rcon_cmd:document.getElementById("lo-cmd").value,enabled:document.getElementById("lo-enabled").value==="1"};var url=A+"/lottery/"+sgid;try{if(pid>0){await pjt(url+"/"+pid,d)}else{await pj(url,d)}document.getElementById("lo-modal").remove();toast("已保存");loLo()}catch(e){toast(e.message,true)}}
async function delLo(pid){if(!confirm("确定删除此奖品？"))return;try{await fetch(A+"/lottery/"+glo+"/"+pid,{method:"DELETE"});toast("已删除");loLo()}catch(e){toast(e.message,true)}}
/* ====== 积分兑换 ====== */
var gex="";
async function loEx(){var g=await fj(A+"/groups?filter_web_mgmt=1");var gOpts='<option value="">选择群聊...</option>';for(var id in g){var nm=gn(g[id]);gOpts+='<option value="'+id+'" '+(id===gex?'selected':'')+'>'+(nm||'群 '+id)+'</option>'}var h='<div class="ct"><h3>💱 积分兑换管理</h3><div class="fb"><select onchange="gex=this.value;loEx()" style="width:200px">'+gOpts+'</select><button class="b1 bsm" onclick="showExModal()" style="margin-left:8px">➕ 添加兑换项</button></div>';if(gex){var items=await fj(A+"/exchange/"+gex);if(!items||!items.length){h+='<div class="emp">该群暂无兑换项</div>'}else{h+='<table style="margin-top:12px"><tr><th>编号</th><th>名称</th><th>描述</th><th>积分</th><th>RCON命令</th><th>状态</th><th>操作</th></tr>';for(var i=0;i<items.length;i++){var it=items[i];h+='<tr><td>'+it.id+'</td><td>'+it.name+'</td><td>'+(it.description||'-')+'</td><td>'+it.cost_points+'</td><td><code style="font-size:10px">'+it.rcon_cmd+'</code></td><td>'+(it.enabled?'<span style="color:var(--s)">启用</span>':'<span style="color:var(--d)">关闭</span>')+'</td><td><button class="bw bsm" onclick="showExModal('+it.id+')">编辑</button><button class="bd bsm" onclick="delEx('+it.id+')">删除</button></td></tr>'}h+='</table>'}}else{h+='<div class="emp">请先选择一个群聊</div>'}h+='</div>';document.getElementById("main").innerHTML=h}
async function showExModal(eid){var g=await fj(A+"/groups?filter_web_mgmt=1");var gOpts='<option value="">选择群聊...</option>';for(var id in g){var nm=gn(g[id]);gOpts+='<option value="'+id+'" '+(id===gex?'selected':'')+'>'+(nm||'群 '+id)+'</option>'}var it={group_id:gex||"",name:"",description:"",rcon_cmd:"",cost_points:0,enabled:1};var isEdit=false;if(eid){isEdit=true;var items=await fj(A+"/exchange/"+gex);for(var i=0;i<items.length;i++){if(items[i].id===eid){it=items[i];break}}}var h='<div class="mbg" id="ex-modal" onclick="if(event.target===this)this.remove()"><div class="mod"><h3>'+(isEdit?'编辑':'添加')+'兑换项</h3><div class="fg"><label>所属群聊</label><select id="ex-gid" '+(isEdit?'disabled':'')+'>'+gOpts+'</select></div><div class="fg"><label>名称</label><input id="ex-name" value="'+it.name+'"></div><div class="fg"><label>描述</label><input id="ex-desc" value="'+(it.description||'')+'"></div><div class="fg"><label>积分消耗</label><input type="number" id="ex-cost" value="'+it.cost_points+'"></div><div class="fg"><label>RCON命令 ({player}=玩家MC ID)</label><input id="ex-cmd" value="'+(it.rcon_cmd||'')+'"></div><div class="fg"><label>启用</label><select id="ex-enabled"><option value="1" '+(it.enabled?'selected':'')+'>是</option><option value="0" '+(!it.enabled?'selected':'')+'>否</option></select></div><div style="margin-top:12px"><button class="b1 bs" onclick="saveEx('+(isEdit?eid:0)+')">保存</button><button class="b2 bs" onclick="document.getElementById(\'ex-modal\').remove()" style="margin-left:8px">取消</button></div></div></div>';document.body.insertAdjacentHTML("beforeend",h)}
async function saveEx(eid){var sgid=gex;if(eid===0)sgid=document.getElementById("ex-gid").value;var d={group_id:sgid,name:document.getElementById("ex-name").value,description:document.getElementById("ex-desc").value,cost_points:parseInt(document.getElementById("ex-cost").value)||0,rcon_cmd:document.getElementById("ex-cmd").value,enabled:document.getElementById("ex-enabled").value==="1"};var url=A+"/exchange/"+sgid;try{if(eid>0){await pjt(url+"/"+eid,d)}else{await pj(url,d)}document.getElementById("ex-modal").remove();toast("已保存");loEx()}catch(e){toast(e.message,true)}}
async function delEx(eid){if(!confirm("确定删除此兑换项？"))return;try{await fetch(A+"/exchange/"+gex+"/"+eid,{method:"DELETE"});toast("已删除");loEx()}catch(e){toast(e.message,true)}}
/* ====== 补偿管理 ====== */
var cf="pending";
async function loCm(f){if(f!==undefined)cf=f||"pending";var g=await fj(A+"/groups?filter_web_mgmt=1"),c=await fj(A+"/compensations?status="+cf+"&limit=100"),cnt={'all':0,pending:0,approved:0,rejected:0};try{var ct=await fj(A+"/compensations/count");Object.assign(cnt,ct)}catch(e){}var h='<div class="fb" style="margin-bottom:12px"><h3 style="margin:0">补偿管理</h3></div><div class="fbar"><button class="bsm '+(cf==='pending'?'bw':'b2')+'" onclick="loCm(\'pending\')">待处理 ('+cnt.pending+')</button><button class="bsm '+(cf==='approved'?'bg':'b2')+'" onclick="loCm(\'approved\')">已通过 ('+cnt.approved+')</button><button class="bsm '+(cf==='rejected'?'bd':'b2')+'" onclick="loCm(\'rejected\')">已拒绝 ('+cnt.rejected+')</button><button class="bsm '+(cf==='all'?'b1':'b2')+'" onclick="loCm(\'all\')">全部 ('+cnt.all+')</button></div>';if(!c||!c.length){h+='<div class="emp">暂无补偿记录</div>'}else{h+='<div class="ct"><table><tr><th>编号</th><th>QQ号</th><th>MC ID</th><th>群聊</th><th>描述</th><th>RCON命令</th><th>申请时间</th><th>状态</th><th>操作</th></tr>';for(var i=0;i<c.length;i++){var r=c[i],ts=r.time?new Date(r.time*1000).toLocaleString("zh-CN"):"-",st="t-"+r.status.charAt(0),grp=gn(g[r.group_id]||[]);h+='<tr><td>'+r.id+'</td><td>'+r.qq_id+'</td><td>'+r.mc_id+'</td><td>'+(grp||(r.group_id?'群 '+r.group_id:'-'))+'</td><td>'+(r.description||'-')+'</td><td><code style="font-size:10px">'+(r.rcon_cmd||'-')+'</code></td><td>'+ts+'</td><td><span class="t1 '+st+'">'+(r.status==='approved'?'已通过':r.status==='rejected'?'已拒绝':'待处理')+'</span></td><td>'+(r.status==='pending'?'<button class="bg bsm" onclick="apC('+r.id+')">通过</button><button class="bd bsm" onclick="rjC('+r.id+')">拒绝</button>':'-')+'</td></tr>'}h+='</table></div>'}document.getElementById("main").innerHTML=h}
async function apC(id){await fetch(A+"/compensations/"+id+"/approve",{method:"POST"});toast("已通过");loCm()}
async function rjC(id){await fetch(A+"/compensations/"+id+"/reject",{method:"POST"});toast("已拒绝");loCm()}
/* ====== 在线列表 (卡片视图) ====== */
var avatarColors=["#e94560","#2ecc71","#3498db","#f39c12","#9b59b6","#1abc9c","#e74c3c","#34495e","#e67e22","#2980b9","#27ae60","#8e44ad"];
var og="";
function getInitials(n){if(!n)return"?";return n.substring(0,2).toUpperCase()}
function getAvatarColor(n){var h=0;for(var i=0;i<n.length;i++)h=n.charCodeAt(i)+((h<<5)-h);return avatarColors[Math.abs(h)%avatarColors.length]}
async function loOn(){try{var cfg=await fj(A+"/config/all");window._cfg_online_history_max_bars=cfg.online_history_max_bars||70}catch(e){}var u=A+"/online";if(og)u+="?gid="+og;var raw=await fj(u),o=raw.online||raw,rk=null;try{rk=await fj(A+"/online_ranking?limit=20")}catch(e){}var g=await fj(A+"/groups?filter_web_mgmt=1");var gOpts='<option value="">全部群聊</option>';for(var id in g){var nm=gn(g[id]);gOpts+='<option value="'+id+'" '+(id===og?'selected':'')+'>'+(nm||'群 '+id)+'</option>'}var h='<div class="fb" style="margin-bottom:14px"><h3 style="margin:0">当前在线玩家</h3><div style="display:flex;align-items:center;gap:8px"><select onchange="og=this.value;loOn()" style="width:160px">'+gOpts+'</select><button class="b2 bsm" onclick="refreshOnline()">刷新</button></div></div>';if(!o||!Object.keys(o).length){h+='<div class="emp">暂无玩家在线</div>'}else{var t=0;for(var k in o)t+=Object.keys(o[k]||{}).length;h+='<div style="color:var(--m);font-size:12px;margin-bottom:14px">共 '+t+' 名玩家在线</div>';for(var sid in o){var pl=o[sid]||{},kn=Object.keys(pl),sn=kn.length>0&&pl[kn[0]].server_name?pl[kn[0]].server_name:sid;h+='<div class="ct"><h3>🖥️ '+sn+'<span class="badge">'+kn.length+'人</span></h3><div class="oc-grid">';for(var nm in pl){var pp=pl[nm],mins=pp.session_minutes||0,hours=Math.floor(mins/60),rmins=mins%60,durTxt=hours>0?hours+"时"+rmins+"分":rmins+"分",pct=Math.min(100,mins>0?Math.round(mins/720*100):5),bgc=getAvatarColor(nm),loginAt=pp.login_at?new Date(pp.login_at*1000).toLocaleTimeString("zh-CN",{hour:"2-digit",minute:"2-digit"}):"-";h+='<div class="oc" onclick="showPlayerDetail(\''+nm.replace(/'/g,"\\'")+'\')" style="cursor:pointer" title="点击查看详情"><div class="oc-av" style="background:'+bgc+'">'+getInitials(nm)+'</div><div class="oc-info"><div class="oc-name">'+nm+'</div><div class="oc-dur">⏱ '+durTxt+' | 登录 '+loginAt+'</div><div class="oc-bar"><div class="oc-bar-fill" style="width:'+pct+'%;background:'+bgc+'"></div></div></div></div>'}h+='</div></div>'}}if(rk&&rk.length){h+='<div class="ct" style="margin-top:12px"><div class="fb" style="margin-bottom:8px"><h3 style="margin:0">📊 在线时长排行 Top20</h3><button class="bd bsm" onclick="resetRanking()">重置排行</button></div><table><tr><th>排名</th><th>服务器</th><th>玩家</th><th>总在线时长</th></tr>';for(var i=0;i<rk.length;i++){var r=rk[i],hh=Math.floor((r.total||0)/3600),mm=Math.floor(((r.total||0)%3600)/60);h+='<tr><td>'+(i+1)+'</td><td>'+(r.server_name||'-')+'</td><td>'+(r.player_name||'-')+'</td><td>'+hh+'小时'+mm+'分钟</td></tr>'}h+='</table></div>'}var maxBars=window._cfg_online_history_max_bars||70;try{var oh=await fj(A+"/online_history?limit="+maxBars);if(oh&&oh.length){var maxM=1;for(var i=0;i<oh.length;i++){maxM=Math.max(maxM,oh[i].minutes||0)}h+='<div class="ct" style="margin-top:14px;overflow:visible"><h3>📈 在线时长记录 (最近'+oh.length+'条)</h3><div class="oh-chart" style="padding-bottom:40px">';for(var i=0;i<oh.length;i++){var ri=oh[i],m=ri.minutes||0,hgt=Math.max(8,(m/maxM)*260),bgc=getAvatarColor(ri.player_name||"?"),mf=Math.floor(m),durTxt=mf>=60?Math.floor(mf/60)+'时'+(mf%60)+'分':mf+'分';h+='<div class="oh-bar" style="height:'+hgt+'px;background:'+bgc+'"><div class="oh-tip">'+ri.player_name+' @ '+(ri.server_name||'?')+'<br>'+ri.start_fmt+' ~ '+ri.end_fmt+'<br>'+durTxt+'</div></div>'}h+='</div></div>'}}catch(e){}document.getElementById("main").innerHTML=h;refresh(15000,loOn)}
async function refreshOnline(){toast("正在查询在线玩家...");try{var r=await pj(A+"/online/refresh",{});var parts=[];if(r.servers_ok>0)parts.push(r.servers_ok+"个服务器查询成功");if(r.servers_err>0)parts.push(r.servers_err+"个失败");parts.push("发现"+r.total_found+"人在线");toast("刷新完成: "+parts.join("，"))}catch(e){var msg=e.message;try{var j=JSON.parse(msg);msg=j.error||msg}catch(x){}toast(msg,true)}loOn()}
async function resetRanking(){if(!confirm("确定要重置所有在线时长排行数据吗？此操作不可撤销。"))return;try{var r=await pj(A+"/online_ranking/reset",{});toast("已重置，删除了 "+r.deleted+" 条记录");loOn()}catch(e){var msg=e.message;try{var j=JSON.parse(msg);msg=j.error||msg}catch(x){}toast(msg,true)}}
async function showPlayerDetail(playerName){var resp=await fj(A+"/online"),o=resp.online||resp;var sessions=[];var totalMin=0;for(var sid in o){var pl=o[sid]||{};if(pl[playerName]){var pp=pl[playerName];sessions.push({server:sid,login_at:pp.login_at,session_minutes:pp.session_minutes||0});totalMin+=pp.session_minutes||0}}var hh=Math.floor(totalMin/60),mm=totalMin%60;var h='<div class="mbg" id="pd-m" onclick="if(event.target===this)this.remove()"><div class="mod"><h3>👤 '+playerName+'</h3><p style="color:var(--m);margin-bottom:8px">当前总在线: '+hh+'小时'+mm+'分钟</p>';if(sessions.length>0){h+='<table><tr><th>服务器</th><th>登录时间</th><th>在线时长</th></tr>';for(var i=0;i<sessions.length;i++){var s=sessions[i],sh=Math.floor(s.session_minutes/60),sm=s.session_minutes%60,lt=s.login_at?new Date(s.login_at*1000).toLocaleString("zh-CN"):"-";h+='<tr><td>'+s.server+'</td><td>'+lt+'</td><td>'+sh+'时'+sm+'分</td></tr>'}h+='</table>'}else{h+='<p style="color:var(--m)">该玩家当前不在线</p>'}try{var rk=await fj(A+"/online_ranking?limit=50");if(rk){for(var i=0;i<rk.length;i++){if(rk[i].player_name===playerName){var rh=Math.floor((rk[i].total||0)/3600),rm=Math.floor(((rk[i].total||0)%3600)/60);h+='<p style="margin-top:10px;color:var(--s)">📊 历史总在线: '+rh+'小时'+rm+'分钟 (排名 #'+(i+1)+')</p>';break}}}var oh=await fj(A+"/online_history?limit=200");if(oh){var ph=[];for(var i=0;i<oh.length;i++){if(oh[i].player_name===playerName)ph.push(oh[i])}if(ph.length>0){h+='<h4 style="margin-top:12px;color:var(--a)">📜 最近在线记录</h4><table><tr><th>服务器</th><th>上线</th><th>下线</th><th>时长</th></tr>';for(var i=0;i<Math.min(ph.length,20);i++){var r=ph[i];h+='<tr><td>'+r.server_name+'</td><td>'+r.start_fmt+'</td><td>'+r.end_fmt+'</td><td>'+Math.floor(r.minutes)+'分钟</td></tr>'}h+='</table>'}}}catch(e){}h+='<button class="b2 bs" style="margin-top:12px" onclick="document.getElementById(\'pd-m\').remove()">关闭</button></div></div>';document.body.insertAdjacentHTML("beforeend",h)}
/* ====== 审计日志 ====== */
async function loAu(pg,cat,ctx){pg=pg||1;cat=cat||(ctx?ctx.cat:"");var fs=ctx||{cat:"",kw:"",et:"",tf:0,tt:0};if(!ctx){loAu._fs=fs;}else{loAu._fs=fs;}var qs="limit=50&offset="+((pg-1)*50);if(cat)qs+="&category="+cat;if(fs.kw)qs+="&keyword="+encodeURIComponent(fs.kw);if(fs.et)qs+="&event_type="+fs.et;if(fs.tf)qs+="&time_from="+fs.tf;if(fs.tt)qs+="&time_to="+fs.tt;var g=await fj(A+"/groups"),d=await fj(A+"/audit?"+qs),entries=d.entries||[],total=d.total||0,tp=Math.ceil(total/50),h='<div id="au-top" style="margin-bottom:16px"><h3 style="margin:0 0 10px 0">审计日志 (共'+total+'条)</h3><div class="fbar" style="margin-bottom:6px"><input id="akw" placeholder="搜索关键词" value="'+hx(fs.kw)+'" style="width:140px" oninput="loAu_li()" onkeydown="if(event.key==\'Enter\')loAu_s()"><input id="aet" placeholder="事件类型" value="'+hx(fs.et)+'" style="width:80px" oninput="loAu_li()"><input id="atf" type="date" style="width:110px"><input id="att" type="date" style="width:110px"><button class="b1 bsm" onclick="loAu_s()">搜索</button><button class="b2 bsm" onclick="loAu_s(1)">Reset</button><button class="bw bsm" onclick="loAu_exp(\'csv\')">CSV</button><button class="bw bsm" onclick="loAu_exp(\'json\')">JSON</button><button class="b3 bsm" onclick="loAu_del()">删除本页</button></div>';var catNames={cmd:"命令",web:"Web操作",web_rcon:"Web命令",event_macro:"事件宏",online_duration_macro:"在线时长宏",online_trigger:"上线触发",relay:"群服转发",game_notify:"游戏提醒"},catBtns='<div class="fbar"><button class="bsm '+(cat===""?"bw":"b2")+'" onclick="var f=loAu._fs||{};loAu(1,\'\',{cat:\'\',kw:f.kw,et:f.et,tf:f.tf,tt:f.tt})">全部</button>';["cmd","web","web_rcon","event_macro","online_duration_macro","online_trigger","relay","game_notify"].forEach(function(c){catBtns+='<button class="bsm '+(cat===c?"b1":"b2")+'" onclick="var f=loAu._fs||{};loAu(1,\''+c+'\',{cat:\''+c+'\',kw:f.kw,et:f.et,tf:f.tf,tt:f.tt})">'+((catNames[c]||c).slice(0,5))+'</button>'});h+=catBtns+'</div><div id="au-res">';if(!entries.length){h+='<div class="emp">暂无匹配的审计日志</div>'}else{h+='<div class="ct"><table><tr><th style="width:12px"><input type="checkbox" onclick="loAu_ca(this)"></th><th>时间</th><th>类型</th><th>QQ号</th><th>昵称</th><th>群聊</th><th>操作</th><th>结果</th><th>详情</th></tr>';for(var i=0;i<entries.length;i++){var r=entries[i],ts=r.time?new Date(r.time*1000).toLocaleString("zh-CN"):"-",grp=gn(g[r.group_id]||[]),ct=r.category||"cmd",cn=catNames[ct]||ct;h+='<tr><td><input type="checkbox" value="'+r.id+'" class="lac"></td><td>'+ts+'</td><td><span class="badge" style="font-size:10px">'+cn+'</span>'+(r.event_type?' <span style="font-size:9px;color:#aaa">'+r.event_type+'</span>':'')+'</td><td>'+r.sender_id+'</td><td>'+r.sender_name+'</td><td>'+(grp||(r.group_id?"群"+r.group_id:"-"))+'</td><td style="max-width:180px;overflow:hidden"><code style="font-size:10px;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:block" title="'+hx(r.cmd||"").replace(/"/g,"&quot;")+'">'+hx(r.cmd||"")+'</code></td><td><span class="t1 '+(r.ok?"t-on":"t-off")+'">'+(r.ok?"成功":"失败")+'</span></td><td style="max-width:200px;font-size:10px">'+(r.resp||"").slice(0,80)+'</td></tr>'}h+='</table></div>'}var pgs='<div class="fbar" style="margin-top:8px"><span style="font-size:12px">第'+pg+'/'+tp+'页</span>';for(var j=1;j<=Math.min(tp,10);j++){pgs+='<button class="bsm '+(j===pg?"b1":"b2")+'" onclick="loAu('+j+',\''+cat+'\')">'+j+'</button>'}if(tp>10)pgs+='<span style="font-size:11px;color:#aaa">...共'+tp+'页</span>';h+=pgs+'</div>';document.getElementById("main").innerHTML=h;refresh(30000,loAu)}function loAu_li(){clearTimeout(loAu._t);loAu._t=setTimeout(async function(){var kw=document.getElementById("akw").value.trim(),et=document.getElementById("aet").value.trim(),tf=document.getElementById("atf").value?Math.floor(new Date(document.getElementById("atf").value).getTime()/1000):0,tt=document.getElementById("att").value?Math.floor(new Date(document.getElementById("att").value).getTime()/1000+86399):0,fs=loAu._fs||{},cat=fs.cat||"",qs="limit=50&offset=0";if(cat)qs+="&category="+cat;if(kw)qs+="&keyword="+encodeURIComponent(kw);if(et)qs+="&event_type="+et;if(tf)qs+="&time_from="+tf;if(tt)qs+="&time_to="+tt;loAu._fs={cat:cat,kw:kw,et:et,tf:tf,tt:tt};var d=await fj(A+"/audit?"+qs),entries=d.entries||[],total=d.total||0,tp=Math.ceil(total/50),res="";if(!entries.length){res='<div class="emp">暂无匹配的审计日志</div>'}else{var catNames={cmd:"命令",web:"Web操作",web_rcon:"Web命令",event_macro:"事件宏",online_duration_macro:"在线时长宏",online_trigger:"上线触发",relay:"群服转发",game_notify:"游戏提醒"};res='<div class="ct"><table><tr><th style="width:12px"><input type="checkbox" onclick="loAu_ca(this)"></th><th>时间</th><th>类型</th><th>QQ号</th><th>昵称</th><th>群聊</th><th>操作</th><th>结果</th><th>详情</th></tr>';for(var i=0;i<entries.length;i++){var r=entries[i],ts=r.time?new Date(r.time*1000).toLocaleString("zh-CN"):"-",ct=r.category||"cmd",cn=catNames[ct]||ct;res+='<tr><td><input type="checkbox" value="'+r.id+'" class="lac"></td><td>'+ts+'</td><td><span class="badge" style="font-size:10px">'+cn+'</span>'+(r.event_type?' <span style="font-size:9px;color:#aaa">'+r.event_type+'</span>':'')+'</td><td>'+r.sender_id+'</td><td>'+r.sender_name+'</td><td>'+((r.group_id?"群"+r.group_id:"-"))+'</td><td style="max-width:180px;overflow:hidden"><code style="font-size:10px;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:block" title="'+hx(r.cmd||"").replace(/"/g,"&quot;")+'">'+hx(r.cmd||"")+'</code></td><td><span class="t1 '+(r.ok?"t-on":"t-off")+'">'+(r.ok?"成功":"失败")+'</span></td><td style="max-width:200px;font-size:10px">'+(r.resp||"").slice(0,80)+'</td></tr>'}res+='</table></div>'}res+='<div class="fbar" style="margin-top:8px"><span style="font-size:12px">第1/'+tp+'页</span>';for(var j=1;j<=Math.min(tp,10);j++){res+='<button class="bsm '+(j===1?"b1":"b2")+'" onclick="loAu('+j+',\''+cat+'\')">'+j+'</button>'}if(tp>10)res+='<span style="font-size:11px;color:#aaa">...共'+tp+'页</span>';res+='</div>';var el=document.getElementById("au-res");if(el)el.innerHTML=res;var h3=document.querySelector("#au-top h3");if(h3)h3.textContent="审计日志 (共"+total+"条)"},300)}function loAu_s(pg){pg=pg||1;var kw=document.getElementById("akw").value.trim(),et=document.getElementById("aet").value.trim(),tf=document.getElementById("atf").value?Math.floor(new Date(document.getElementById("atf").value).getTime()/1000):0,tt=document.getElementById("att").value?Math.floor(new Date(document.getElementById("att").value).getTime()/1000+86399):0;loAu(1,"",{cat:"",kw:kw,et:et,tf:tf,tt:tt})}function loAu_ca(cb){var cs=document.querySelectorAll(".lac");for(var i=0;i<cs.length;i++)cs[i].checked=cb.checked}async function loAu_exp(fmt){var fs=loAu._fs||{},qs="format="+fmt;if(fs.kw)qs+="&keyword="+encodeURIComponent(fs.kw);if(fs.cat)qs+="&category="+fs.cat;if(fs.et)qs+="&event_type="+fs.et;if(fs.tf)qs+="&time_from="+fs.tf;if(fs.tt)qs+="&time_to="+fs.tt;var url=A+"/audit/export?"+qs;window.open(url,"_blank")}async function loAu_del(){var cs=document.querySelectorAll(".lac:checked"),ids=[];for(var i=0;i<cs.length;i++)ids.push(parseInt(cs[i].value));if(!ids.length){alert("请勾选要删除的条目");return}if(!confirm("确认删除选中的 "+ids.length+" 条审计日志？"))return;var r=await fetch(A+"/audit/delete",{method:"POST",body:JSON.stringify({ids:ids})});var d=await r.json();if(d.deleted)loAu();else alert("删除失败: "+(d.error||"未知错误"))}
/* ====== 宏命令 ====== */
async function loMa(){var m=await fj(A+"/macros"),em=await fj(A+"/event-macros"),h='<div class="fb" style="margin-bottom:12px"><h3 style="margin:0">宏命令管理</h3><button class="b1 bsm" onclick="adMac()">+ 新建宏</button></div>';for(var n in m){var mc=m[n],cmds=mc.commands||mc,en=mc.enabled!==false;h+='<div class="ct"><div style="display:flex;justify-content:space-between;align-items:flex-start"><div style="flex:1"><h3 style="margin:0 0 4px">'+n+'<label class="tg" style="margin-left:8px;vertical-align:middle"><input type="checkbox" '+(en?'checked':'')+' onchange="tglMa(\''+n.replace(/'/g,"\\'")+'\',this.checked)"><span class="sl"></span></label><span style="color:var(--m);font-size:10px;margin-left:6px">'+(en?'启用':'禁用')+'</span><span class="badge" style="margin-left:6px">'+cmds.length+'条命令</span></h3><pre style="margin:4px 0 0">'+cmds.join("\n")+'</pre></div><div class="ac"><button class="b1 bsm" onclick="execMacro(\''+n.replace(/'/g,"\\'")+'\')">▶ 执行</button><button class="bw bsm" onclick="edMac(\''+n.replace(/'/g,"\\'")+'\')">编辑</button><button class="bd bsm" onclick="rmMac(\''+n.replace(/'/g,"\\'")+'\')">删除</button></div></div></div>'}if(!Object.keys(m).length)h+='<div class="emp">暂无宏命令</div>';h+='<hr style="border:1px solid var(--b);margin:20px 0"><div class="fb" style="margin-bottom:12px"><h3 style="margin:0">🪝 日志事件宏</h3><button class="b1 bsm" onclick="adEm()">+ 新建宏</button><button class="b2 bsm" style="margin-left:4px" onclick="expEm()">📤 导出</button><button class="b2 bsm" style="margin-left:2px" onclick="impEm()">📥 导入</button><span style="color:var(--m);font-size:11px;margin-left:8px">日志事件→自动RCON</span></div>';h+='<div class="ct" style="margin-bottom:14px"><div style="display:flex;align-items:flex-start;gap:4px"><span style="color:var(--a);font-size:16px">ℹ️</span><div style="flex:1"><strong style="color:var(--a)">说明</strong><p style="color:var(--m);font-size:12px;line-height:1.8;margin:2px 0">日志事件宏监控<strong style="color:var(--a)">latest.log</strong>文件实时响应游戏事件，自动在指定服务器执行 RCON 命令。需先在<strong style="color:var(--a)">服务器管理</strong>中填写对应服务器的日志路径，并在<strong style="color:var(--a)">全局设置→在线追踪</strong>中开启"RCON 日志监听"。</p><details style="margin-top:4px"><summary style="color:var(--s);font-size:11px;cursor:pointer">📖 参数说明</summary><p style="color:var(--m);font-size:12px;line-height:1.8;margin:6px 0 0">• <strong>前延时(秒)</strong>：事件触发后，<span style="color:#fa0">等待 X 秒再执行命令</span>（非"事件发生前"）。如玩家加入 → 等5秒 → 执行欢迎。<br>• <strong>后延时(秒)</strong>：<span style="color:#fa0">命令执行完后等待 X 秒</span>（非"事件发生后"）。用于多事件顺序延时间隔。<br>• <strong>独立命令</strong>：设前/后延时后展开，每个事件类型可配专属 RCON 命令；为空则用全局命令。<br>• <strong>全局命令</strong>：当事件类型未配独立命令时使用的共享命令。<br>• <strong>逻辑门</strong>：AND=所有条件满足才触发 / OR=任一条件满足即触发，配合下方条件使用。<br>• <strong>冷却时间</strong>：两次触发之间的最小间隔秒数（0=无冷却）。<br>• <strong>频率限制</strong>：指定时间窗口内最多触发次数（0=不限）。<br>• <strong>QQ通知</strong>：触发时发送到QQ群的消息，支持下方变量。<br>• <strong>事件参数</strong>：匹配日志行内容关键词（如 diamond_sword），不区分大小写。</p></details><details style="margin-top:4px"><summary style="color:#fa0;font-size:11px;cursor:pointer">🔄 say / tell / msg 命令自动转换</summary><p style="color:var(--m);font-size:12px;line-height:1.8;margin:6px 0 0">事件宏中使用 <code style="background:var(--bg);padding:2px 5px">say</code> / <code style="background:var(--bg);padding:2px 5px">tell</code> / <code style="background:var(--bg);padding:2px 5px">msg</code> 命令时，插件会自动转换为 <code style="background:var(--bg);padding:2px 5px">tellraw</code>，避免 Minecraft 默认的 <span style="color:#fa0">[Server]</span> 或 <span style="color:#fa0">Rcon 悄悄对你说</span> 前缀。<br><br><span style="color:var(--a)">转换规则：</span><br>• <code style="background:var(--bg);padding:2px 5px">say &lt;消息&gt;</code> → <code style="background:var(--bg);padding:2px 5px">tellraw @a {"text":"&lt;前缀&gt; &lt;消息&gt;"}</code><br>• <code style="background:var(--bg);padding:2px 5px">tell &lt;目标&gt; &lt;消息&gt;</code> → <code style="background:var(--bg);padding:2px 5px">tellraw &lt;目标&gt; {"text":"&lt;前缀&gt; &lt;消息&gt;"}</code><br>• <code style="background:var(--bg);padding:2px 5px">msg &lt;目标&gt; &lt;消息&gt;</code> → <code style="background:var(--bg);padding:2px 5px">tellraw &lt;目标&gt; {"text":"&lt;前缀&gt; &lt;消息&gt;"}</code><br><br><span style="color:var(--m)">前缀来自<strong>全局设置→通用配置→事件宏游戏前缀</strong>（</span><code style="background:var(--bg);padding:2px 5px;color:var(--s)">event_macro_game_prefix</code><span style="color:var(--m)">），无配置时不执行转换。</span></p></details><details style="margin-top:4px"><summary style="color:var(--s);font-size:11px;cursor:pointer">📋 可用变量对照</summary><table style="font-size:11px;margin-top:6px;border-collapse:collapse;width:100%;color:var(--m)"><tr style="background:var(--bg)"><th style="padding:3px 8px;text-align:left;border:1px solid var(--b)">变量</th><th style="padding:3px 8px;text-align:left;border:1px solid var(--b)">说明</th><th style="padding:3px 8px;text-align:left;border:1px solid var(--b)">可用于</th></tr><tr><td style="padding:3px 8px;border:1px solid var(--b)"><code>{player}</code></td><td style="padding:3px 8px;border:1px solid var(--b)">触发的玩家名（小写）</td><td style="padding:3px 8px;border:1px solid var(--b)">RCON命令 / QQ消息</td></tr><tr style="background:var(--bg)"><td style="padding:3px 8px;border:1px solid var(--b)"><code>{PLAYER}</code></td><td style="padding:3px 8px;border:1px solid var(--b)">触发的玩家名（原大小写）</td><td style="padding:3px 8px;border:1px solid var(--b)">RCON命令</td></tr><tr><td style="padding:3px 8px;border:1px solid var(--b)"><code>{mc_id}</code></td><td style="padding:3px 8px;border:1px solid var(--b)">玩家绑定的 MC ID</td><td style="padding:3px 8px;border:1px solid var(--b)">RCON命令 / QQ消息</td></tr><tr style="background:var(--bg)"><td style="padding:3px 8px;border:1px solid var(--b)"><code>{qq}</code></td><td style="padding:3px 8px;border:1px solid var(--b)">玩家绑定的 QQ 号</td><td style="padding:3px 8px;border:1px solid var(--b)">RCON命令 / QQ消息</td></tr><tr><td style="padding:3px 8px;border:1px solid var(--b)"><code>{server}</code></td><td style="padding:3px 8px;border:1px solid var(--b)">当前服务器名称</td><td style="padding:3px 8px;border:1px solid var(--b)">QQ消息</td></tr><tr style="background:var(--bg)"><td style="padding:3px 8px;border:1px solid var(--b)"><code>{event_type}</code></td><td style="padding:3px 8px;border:1px solid var(--b)">事件类型（如 player_join）</td><td style="padding:3px 8px;border:1px solid var(--b)">QQ消息</td></tr><tr><td style="padding:3px 8px;border:1px solid var(--b)"><code>{event_param}</code></td><td style="padding:3px 8px;border:1px solid var(--b)">事件参数（如物品名）</td><td style="padding:3px 8px;border:1px solid var(--b)">QQ消息</td></tr></table></details></div></div></div>';if(!em||!em.length){h+='<div class="emp">暂无事件宏。添加示例：检测"玩家死亡"→执行RCON命令</div>'}else{for(var i=0;i<em.length;i++){var v=em[i];h+='<div class="ct"><div style="display:flex;justify-content:space-between;align-items:flex-start"><div style="flex:1"><strong>'+(v.name||'?')+'</strong>';h+='<label class="tg" style="margin-left:8px;vertical-align:middle"><input type="checkbox" '+(v.enabled?'checked':'')+' onchange="tglEm('+i+',this.checked)"><span class="sl"></span></label>';h+='<span style="color:var(--m);font-size:10px;margin-left:6px">'+(v.enabled?'启用':'禁用')+'</span>';h+=(function(ets){var n={player_first_join:'首次加入',player_join:'加入',player_leave:'退出',player_kick:'被踢',player_death_pvp:'PVP击杀',player_death:'死亡',player_first_death:'首次死亡',player_respawn:'复活',player_advancement:'成就',player_item_get:'物品',server_start:'启动',server_stop:'关闭',server_reload:'重载',boss_kill:'Boss击杀',player_chat:'发言',tps_low:'TPS低',tps_critical:'TPS严重',memory_high:'内存高',server_perf_issue:'性能异常',admin_join:'管理员加入',vip_join:'VIP加入',vip_leave:'VIP退出',vip_death:'VIP死亡'};if(!ets||!ets.length){var et=v.event_type||'';return'<span class="badge" style="margin-left:4px">'+(n[et]||et||'?')+'</span>'}var r='';for(var ei=0;ei<ets.length;ei++){var e=ets[ei],t=typeof e==='object'?e.type||'':e||'',pre=typeof e==='object'?parseFloat(e.pre_delay)||0:0,post=typeof e==='object'?parseFloat(e.post_delay)||0:0,d='';if(pre>0||post>0){d='<span style="font-size:9px;opacity:0.7">(';if(pre>0)d+='前'+pre+'s';if(pre>0&&post>0)d+=' ';if(post>0)d+='后'+post+'s';d+=')</span>'}r+='<span class="badge" style="margin-left:3px;font-size:10px">'+(n[t]||t||'?')+'</span>'+d}return r||'?'})(v.event_types);h+='<span style="color:var(--w);font-size:11px;margin-left:6px">服务器:</span><code>'+(v.server_name||'?')+'</code>';h+='<span style="color:var(--w);font-size:11px;margin-left:8px">冷却:</span>'+(v.cooldown||0)+'s';h+=v.player_name?' <span class="badge" style="background:var(--s)">🎯'+v.player_name+'</span>':'';h+=v.max_triggers>0?' <span style="color:var(--w);font-size:11px;margin-left:6px">频率:</span>'+v.max_triggers+'次/'+(v.trigger_window||0)+'s':'';h+=v.event_param?' <span class="badge" style="background:var(--a);font-size:10px">📋'+v.event_param+'</span>':'';h+=v.qq_message?' <span title="QQ通知已配置" style="color:#fa0;font-size:12px;margin-left:4px;cursor:help">📢</span>':'';h+='</div><div class="ac"><button class="bw bsm" onclick="edEm('+i+')">编辑</button><button class="bd bsm" onclick="delEm('+i+')">删除</button></div></div>';h+=(function(ets){var r='';if(!ets||!ets.length)return'';for(var ei=0;ei<ets.length;ei++){var e=ets[ei];if(typeof e==='object'&&e.commands&&e.commands.length){var n={player_first_join:'首次加入',player_join:'加入',player_leave:'退出',player_kick:'被踢',player_death_pvp:'PVP击杀',player_death:'死亡',player_first_death:'首次死亡',player_respawn:'复活',player_advancement:'成就',player_item_get:'物品',server_start:'启动',server_stop:'关闭',server_reload:'重载',boss_kill:'Boss击杀',player_chat:'发言',tps_low:'TPS低',tps_critical:'TPS严重',memory_high:'内存高',server_perf_issue:'性能异常',admin_join:'管理员加入',vip_join:'VIP加入',vip_leave:'VIP退出',vip_death:'VIP死亡'};r+='<div style="margin-top:6px;padding:4px 8px;background:var(--bg);border-left:3px solid var(--s);border-radius:3px"><strong style="font-size:10px;color:var(--s)">'+(n[e.type]||e.type)+' 独立命令</strong>'+(function(ecmds){var p='';for(var ci=0;ci<ecmds.length;ci++){var c=ecmds[ci],cmd='',dly=0;if(typeof c==='object'){cmd=c.cmd||'';dly=parseFloat(c.delay)||0}else{cmd=c||''}if(!cmd)continue;p+='<div style="font-size:10px;color:var(--a);margin-top:2px;padding-left:4px;border-left:2px solid var(--b)">'+cmd+(dly>0?' <span style="font-size:9px;color:var(--m)">(延时'+dly+'s)</span>':'')+'</div>'}return p})(e.commands)+'</div>'}}return r})(v.event_types);h+='<pre style="margin:6px 0 0;font-size:11px;color:var(--s)">'+((v.commands||[]).join("\n"))+'</pre></div>'}}document.getElementById("main").innerHTML=h;window._macros=m;window._emacros=em}
function adMac(){document.body.insertAdjacentHTML("beforeend",'<div class="mbg" id="mc-m" onclick="if(event.target===this)this.remove()"><div class="mod"><h3>新建宏</h3><div class="fg"><label>宏名称</label><input id="mfn"></div><div class="fg"><label>命令列表(一行一条命令)</label><textarea id="mfc" rows="6"></textarea></div><div class="fr" style="margin-top:14px"><button class="b1 bs" onclick="doMac()">保存</button><button class="b2 bs" onclick="document.getElementById(\'mc-m\').remove()">取消</button></div></div></div>')}
function edMac(name){var mc=(window._macros||{})[name];var cmds=mc?(mc.commands||mc):[];document.body.insertAdjacentHTML("beforeend",'<div class="mbg" id="mc-m" onclick="if(event.target===this)this.remove()"><div class="mod"><h3>编辑宏: '+name+'</h3><div class="fg"><label>命令列表(一行一条命令)</label><textarea id="mfc" rows="6">'+cmds.join("\n")+'</textarea></div><div class="fr" style="margin-top:14px"><button class="b1 bs" onclick="doUpdMac(\''+name.replace(/'/g,"\\'")+'\')">保存</button><button class="b2 bs" onclick="document.getElementById(\'mc-m\').remove()">取消</button></div></div></div>')}
async function doMac(){var n=document.getElementById("mfn").value.trim(),c=document.getElementById("mfc").value.split("\n").map(function(s){return s.trim()}).filter(Boolean);if(!n||!c.length){toast("请填写完整",true);return}await pj(A+"/macros",{name:n,commands:c,enabled:true});document.getElementById("mc-m")?.remove();toast("宏已添加");loMa()}
async function doUpdMac(name){var c=document.getElementById("mfc").value.split("\n").map(function(s){return s.trim()}).filter(Boolean);await pjt(A+"/macros/"+encodeURIComponent(name),{commands:c});document.getElementById("mc-m")?.remove();toast("已更新");loMa()}
async function rmMac(n){if(!confirm("确定要删除宏 '"+n+"' 吗？"))return;await fetch(A+"/macros/"+encodeURIComponent(n),{method:"DELETE"});toast("宏已删除");loMa()}
async function tglMa(name,enabled){try{await pjt(A+"/macros/"+encodeURIComponent(name),{enabled:enabled});toast(enabled?"已启用":"已禁用")}catch(e){toast(e.message,true)}}
function execMacro(name){var mc=(window._macros||{})[name];if(!mc){toast("宏已失效，请刷新页面",true);return}var cmds=mc.commands||mc;if(!cmds||!cmds.length){toast("宏已失效，请刷新页面",true);return}if(mc.enabled===false){toast("该宏已被禁用",true);return}var allParams=[];cmds.forEach(function(c){var p=extractParams(c);p.forEach(function(pp){if(!allParams.some(function(x){return x.key===pp.key}))allParams.push(pp)})});var gid=document.getElementById("cmd-gid")?.value||"";if(!gid){var gs=document.getElementById("cmd-gid");gid=gs?gs.value:Object.keys(window._g||{})[0]||""}var sidx=parseInt(document.getElementById("cmd-sidx")?.value)||0;showExecDlg("执行宏: "+name,cmds,allParams,gid,sidx)}
/* ====== 上线触发器 ====== */
async function loOt(){var t=await fj(A+"/online-triggers");var h='<div class="fb" style="margin-bottom:12px"><h3 style="margin:0">🎯 上线触发器管理</h3><button class="b1 bsm" onclick="adOt()">+ 新建触发器</button></div>';if(!t||!t.length){h+='<div class="emp">暂无触发器，点击上方按钮创建</div><div class="ct" style="margin-top:12px"><h3>ℹ️ 说明</h3><p style="color:var(--m);font-size:12px;line-height:1.8">上线触发器会在<strong style="color:var(--a)">在线追踪轮询</strong>（约每分钟一次）检测到指定玩家上线时，自动执行预设的 RCON 命令。<br>命令中 <code style="background:var(--bg);padding:2px 5px">{player}</code> 会被替换为实际玩家名。<br>示例：玩家 Notch 上线 → 自动执行 <code style="background:var(--bg);padding:2px 5px">/attribute Notch minecraft:generic.movement_speed base set 0.2</code></p></div>'}else{for(var i=0;i<t.length;i++){var v=t[i];h+='<div class="ct"><div style="display:flex;justify-content:space-between;align-items:flex-start"><div style="flex:1"><strong>'+v.name+'</strong>';h+='<label class="tg" style="margin-left:8px;vertical-align:middle"><input type="checkbox" '+(v.enabled?'checked':'')+' onchange="tglOt(\''+v.name.replace(/'/g,"\\'")+'\',this.checked)"><span class="sl"></span></label>';h+='<span style="color:var(--m);font-size:10px;margin-left:6px">'+(v.enabled?'启用':'禁用')+'</span>';if(v.note)h+='<div style="color:var(--m);font-size:11px;margin-top:2px">📝 '+v.note+'</div>';h+='<div style="margin-top:4px"><span style="color:var(--w);font-size:11px">玩家: </span><code style="font-size:12px">'+v.player+'</code>';h+=' <span class="badge">'+(v.match_type==='exact'?'精确匹配':'包含匹配')+'</span>';h+=' <span style="color:var(--w);font-size:11px">冷却: </span>'+v.cooldown_seconds+'秒</div>';h+='<pre style="margin:6px 0 0;font-size:11px;color:var(--s)">'+(v.commands||[]).join("\n")+'</pre></div>';h+='<div class="ac"><button class="bw bsm" onclick="edOt(\''+v.name.replace(/'/g,"\\'")+'\','+i+')">编辑</button><button class="bd bsm" onclick="rmOt(\''+v.name.replace(/'/g,"\\'")+'\')">删除</button></div></div></div>'}}document.getElementById("main").innerHTML=h;window._otriggers=t}
function adOt(){otModal()}
async function otModal(name,idx){var t={};if(idx!==undefined&&window._otriggers)t=window._otriggers[idx]||{};var isEdit=!!name;var plOpts='';try{var pl=await fj(A+"/players");if(pl&&pl.length){var seenMc={};plOpts='<option value="">-- 从数据库选择 --</option>';for(var pi=0;pi<pl.length;pi++){var mc=pl[pi].mc_id;if(mc&&!seenMc[mc]){seenMc[mc]=true;plOpts+='<option value="'+mc+'">'+mc+'</option>'}}}}catch(e){}var m='<div class="mbg" id="ot-m" onclick="if(event.target===this)this.remove()"><div class="mod" style="max-width:600px"><h3>'+(isEdit?'编辑触发器':'新建上线触发器')+'</h3>';m+='<div class="fg"><label>触发器名称 *</label><input id="otn" value="'+(t.name||'')+'"></div>';m+='<div class="fg"><label>备注说明</label><input id="otnote" value="'+(t.note||'')+'" placeholder="如：自动设置移速 0.15"></div>';m+='<div class="fg"><label>目标玩家名 *</label><div style="display:flex;gap:8px"><input id="otpl" value="'+(t.player||'')+'" placeholder="MC 玩家 ID" style="flex:1"><select id="otpl-db" onchange="var s=this.value;if(s)document.getElementById(\'otpl\').value=s" style="width:170px;font-size:11px">'+plOpts+'</select></div></div>';m+='<div class="fr"><div class="fg"><label>匹配方式</label><select id="otmt"><option value="exact" '+(t.match_type!=='contains'?'selected':'')+'>精确匹配</option><option value="contains" '+(t.match_type==='contains'?'selected':'')+'>包含匹配</option></select></div></div>';m+='<div class="fg"><label>触发冷却(秒)</label><input type="number" id="otcd" value="'+(t.cooldown_seconds||300)+'" min="0"></div>';m+='<div class="fg"><label>命令列表(一行一条命令)<br><span style="color:var(--m);font-size:10px">{player} 将被替换为上线玩家名，如 /attribute {player} ... base set 0.15</span></label><textarea id="otc" rows="4" placeholder="/attribute {player} minecraft:generic.movement_speed base set 0.15">'+(t.commands||[]).join("\n")+'</textarea></div>';m+='<div style="margin-top:14px"><button class="b1 bs" onclick="saveOt(\''+(isEdit?t.name.replace(/'/g,"\\'"):'')+'\')">保存</button><button class="b2 bs" onclick="document.getElementById(\'ot-m\').remove()">取消</button></div></div></div>';document.body.insertAdjacentHTML("beforeend",m)}
function edOt(name,idx){otModal(name,idx)}
async function rmOt(name){if(!confirm("确定要删除触发器 '"+name+"' 吗？"))return;await fetch(A+"/online-triggers/"+encodeURIComponent(name),{method:"DELETE"});toast("触发器已删除");loSc()}
async function tglOt(name,enabled){try{await pjt(A+"/online-triggers/"+encodeURIComponent(name),{enabled:enabled});toast(enabled?"已启用":"已禁用")}catch(e){toast(e.message,true)}}
async function saveOt(oldName){var name=document.getElementById("otn").value.trim();var player=document.getElementById("otpl").value.trim();var cmds=document.getElementById("otc").value.split("\n").map(function(s){return s.trim()}).filter(Boolean);if(!name){toast("请输入触发器名称",true);return}if(!player){toast("请输入目标玩家名",true);return}var b={name:name,enabled:true,player:player,match_type:document.getElementById("otmt").value,commands:cmds,cooldown_seconds:parseInt(document.getElementById("otcd").value)||300,note:document.getElementById("otnote").value.trim()};try{if(oldName){if(name!==oldName)b.name=name;await pjt(A+"/online-triggers/"+encodeURIComponent(oldName),b)}else{await pj(A+"/online-triggers",b)}document.getElementById("ot-m")?.remove();toast("触发器已保存");loSc()}catch(e){toast(e.message,true)}}
function adCmdTpl(){cmdTplModal()}
function cmdTplModal(idx){var t=idx!==undefined&&window._ctpls?window._ctpls[idx]:{},params=t.params||[],m='<div class="mbg" id="ct-m" onclick="if(event.target===this)this.remove()"><div class="mod" style="max-width:680px"><h3>'+(idx!==undefined?'编辑模板':'新建命令模板')+'</h3><div class="fg"><label>模板名称 *</label><input id="ctn" value="'+(t.name||'')+'"></div><div class="fg"><label>描述</label><input id="ctd" value="'+(t.desc||'')+'" placeholder="如：设置玩家移动速度"></div><div class="fg"><label>命令模板(一行一条，用 {参数名} 做占位)</label><textarea id="ctc" rows="4">'+(t.commands||[]).join("\n")+'</textarea></div><div class="fg" style="margin-top:8px"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px"><label style="margin:0">参数定义</label><button class="b2 bsm" onclick="addParam()">+ 添加参数</button></div><div id="ct-params">';params.forEach(function(p,i){m+=paramRow(p,i)});m+='</div></div><div style="margin-top:14px"><button class="b1 bs" onclick="saveCmdTpl('+(idx!==undefined?idx:'-1')+')">保存</button><button class="b2 bs" onclick="document.getElementById(\'ct-m\').remove()">取消</button></div></div></div>';document.body.insertAdjacentHTML("beforeend",m);window._tplParams=params||[]}
function paramRow(p,i){p=p||{};return'<div class="fr" style="margin-bottom:4px"><input value="'+(p.key||'')+'" placeholder="参数名(英文)" style="width:100px" onchange="updParam('+i+',\'key\',this.value)"><input value="'+(p.label||'')+'" placeholder="显示标签" style="width:100px" onchange="updParam('+i+',\'label\',this.value)"><input value="'+(p.default||'')+'" placeholder="默认值" style="width:120px" onchange="updParam('+i+',\'default\',this.value)"><button class="bd bsm" onclick="delParam('+i+')">✕</button></div>'}
function updParam(i,f,v){if(!window._tplParams)window._tplParams=[];if(!window._tplParams[i])window._tplParams[i]={key:'',label:'',default:''};window._tplParams[i][f]=v}
function addParam(){window._tplParams=window._tplParams||[];window._tplParams.push({key:'',label:'',default:''});document.getElementById("ct-params").insertAdjacentHTML("beforeend",paramRow({},window._tplParams.length-1))}
function delParam(i){window._tplParams.splice(i,1);var c=document.getElementById("ct-params");var rows=c.querySelectorAll(".fr");if(rows[i])rows[i].remove();for(var j=0;j<window._tplParams.length;j++){var f=rows[j]?.querySelectorAll("input");if(f){f[0].setAttribute("onchange","updParam("+j+",'key',this.value)");f[1].setAttribute("onchange","updParam("+j+",'label',this.value)");f[2].setAttribute("onchange","updParam("+j+",'default',this.value)");var b=rows[j]?.querySelector("button");if(b)b.setAttribute("onclick","delParam("+j+")")}}}
async function saveCmdTpl(idx){var name=document.getElementById("ctn").value.trim(),desc=document.getElementById("ctd").value.trim(),cmds=document.getElementById("ctc").value.split("\n").map(function(s){return s.trim()}).filter(Boolean);var params=(window._tplParams||[]).filter(function(p){return p.key});if(!name){toast("请输入模板名称",true);return}var b={name:name,desc:desc,commands:cmds,params:params};if(idx>=0&&window._ctpls){var old=window._ctpls[idx].name;await pjt(A+"/cmd-templates/"+old,b)}else{await pj(A+"/cmd-templates",b)}document.getElementById("ct-m")?.remove();toast("已保存");loCmd()}
function edCmdTpl(idx){cmdTplModal(idx)}
async function rmCmdTpl(name){if(!confirm("删除模板 "+name+"?"))return;await fetch(A+"/cmd-templates/"+name,{method:"DELETE"});toast("已删除");loCmd()}
async function tglCd(idx,enabled){var t=window._ctpls[idx];if(!t)return;try{await pjt(A+"/cmd-templates/"+encodeURIComponent(t.name),{enabled:enabled});t.enabled=enabled;toast(enabled?"已启用":"已禁用")}catch(e){toast(e.message,true)}}
function execCmdTpl(idx){var t=window._ctpls[idx];if(!t)return;if(t.enabled===false){toast("该模板已被禁用",true);return}var gids=window._g||[],params=t.params||[],m='<div class="mbg" id="exe-m" onclick="if(event.target===this)this.remove()"><div class="mod" style="max-width:500px"><h3>执行: '+t.name+'</h3><div class="fg"><label>目标群</label><select id="xe-gid">';gids.forEach(function(g){m+='<option value="'+g+'">群 '+g+(window._gns?(' ('+window._gns[g]+')'):'')+'</option>'});m+='</select></div><div class="fg" style="font-size:11px;color:var(--m);margin:4px 0 8px">命令: <code>'+t.commands.join(", ")+'</code></div>';params.forEach(function(p){m+='<div class="fg"><label>'+p.label+' (<code>{'+p.key+'}</code>)</label><input id="xe-'+p.key+'" value="'+(p.default||'')+'" placeholder="'+p.label+'"></div>'});m+='<div style="margin-top:14px"><button class="b1 bs" onclick="doExecTpl(\''+idx+'\')">▶ 执行</button><button class="b2 bs" onclick="document.getElementById(\'exe-m\').remove()">取消</button></div></div></div>';document.body.insertAdjacentHTML("beforeend",m)}
async function doExecTpl(idx){var t=window._ctpls[idx];if(!t)return;var gid=document.getElementById("xe-gid").value,params=t.params||[],values={};params.forEach(function(p){values[p.key]=document.getElementById("xe-"+p.key).value});var cmds=t.commands.map(function(c){var s=c;for(var k in values){s=s.split("{"+k+"}").join(values[k])}return s});var r=await pj(A+"/rcon/exec",{group_id:gid,commands:cmds});document.getElementById("exe-m")?.remove();if(r&&r.results){var out=r.results.map(function(x){return x.ok?'✓ '+x.cmd+': '+x.reply:'✗ '+x.cmd+': '+x.error}).join("\n");toast("执行结果:\n"+out,false,8000)}else{toast("执行完成")}}
/* ====== 脚本管理 ====== */
async function loSc(){var s=await fj(A+"/scripts"),t=await fj(A+"/online-triggers"),g=await fj(A+"/groups?filter_web_mgmt=1"),ccGid=window._ccGid||Object.keys(g)[0]||'';if(ccGid&&!g[ccGid])ccGid=Object.keys(g)[0]||'';window._ccGid=ccGid;var cc=ccGid?await fj(A+"/custom-cmds?gid="+ccGid):[],h='<div class="fb" style="margin-bottom:12px"><h3 style="margin:0">📜 脚本管理</h3><button class="b1 bsm" onclick="adSc()">+ 新建脚本</button></div>';if(!s||!s.files||!s.files.length){h+='<div class="emp">暂无脚本文件 ('+(s? s.dir:'')+')</div>'}else{h+='<div style="color:var(--m);font-size:11px;margin-bottom:10px">目录: '+s.dir+' | '+s.files.length+'个文件</div>';for(var i=0;i<s.files.length;i++){var f=s.files[i];var en=f.enabled!==false;h+='<div class="ct"><h3>'+f.name+'<span style="font-size:10px;color:var(--m);margin-left:6px">'+f.size+'B</span><label class="tg" style="margin-left:8px;vertical-align:middle"><input type="checkbox" '+(en?'checked':'')+' onchange="tglSc(\''+f.name.replace(/'/g,"\\'")+'\',this.checked)"><span class="sl"></span></label><span style="color:var(--m);font-size:10px;margin-left:6px">'+(en?'启用':'禁用')+'</span><button class="bd bsm" style="float:right" onclick="rmSc(\''+f.name.replace(/'/g,"\\'")+'\')">删除</button></h3><pre>'+(f.preview||'')+'</pre></div>'}}var gOpts='<option value="">选择群聊...</option>';for(var gid2 in g){var gnm=gn(g[gid2]);gOpts+='<option value="'+gid2+'" '+(gid2===ccGid?'selected':'')+'>'+(gnm||'群 '+gid2)+'</option>'}h+='<hr style="border:1px solid var(--b);margin:20px 0"><div class="fb" style="margin-bottom:12px"><h3 style="margin:0">🔗 自定义命令</h3><select onchange="window._ccGid=this.value;loSc()" style="margin-left:10px;width:160px">'+gOpts+'</select><button class="b1 bsm" onclick="addCc()" style="margin-left:8px">+ 添加命令</button><span style="color:var(--m);font-size:11px;margin-left:8px">/rc自定 &lt;别名&gt;</span></div>';if(!cc||!cc.length){h+='<div class="emp">暂无自定义命令，点击上方按钮创建</div>'}else{h+='<div class="ct"><table><tr><th>别名</th><th>RCON命令</th><th>描述</th><th>启用</th><th>白名单</th><th>回显</th><th>操作</th></tr>';for(var i=0;i<cc.length;i++){var v=cc[i];h+='<tr><td><code>'+v.alias+'</code></td><td><code style="font-size:10px">'+v.rcon_cmd+'</code></td><td>'+(v.description||'-')+'</td><td><label class="tg"><input type="checkbox" '+(v.enabled!==false?'checked':'')+' onchange="tglCc('+i+',this.checked)"><span class="sl"></span></label></td><td><span style="font-size:10px;color:var(--m)">'+(v.whitelist&&v.whitelist.length?v.whitelist.join(', '):'无(全局)')+'</span></td><td><label class="tg"><input type="checkbox" '+(v.show_reply!==false?'checked':'')+' onchange="tglCcReply('+i+',this.checked)"><span class="sl"></span></label></td><td><button class="bw bsm" onclick="edCc('+i+')">编辑</button><button class="bd bsm" onclick="delCc('+i+')">删除</button></td></tr>'}h+='</table></div>'}h+='<hr style="border:1px solid var(--b);margin:20px 0"><div class="fb" style="margin-bottom:12px"><h3 style="margin:0">🎯 上线触发器</h3><button class="b1 bsm" onclick="adOt()">+ 新建触发器</button></div>';if(!t||!t.length){h+='<div class="emp">暂无触发器，点击上方按钮创建</div><div class="ct"><h3>ℹ️ 说明</h3><p style="color:var(--m);font-size:12px;line-height:1.8">上线触发器在<strong style="color:var(--a)">在线追踪轮询</strong>（约每分钟一次）检测到指定玩家上线时自动执行预设 RCON 命令。<br>命令中 <code style="background:var(--bg);padding:2px 5px">{player}</code> 会被替换为玩家名。<br>示例：<code style="background:var(--bg);padding:2px 5px">/attribute {player} minecraft:generic.movement_speed base set 0.2</code></p></div>'}else{for(var i=0;i<t.length;i++){var v=t[i];h+='<div class="ct"><div style="display:flex;justify-content:space-between;align-items:flex-start"><div style="flex:1"><strong>'+v.name+'</strong>';h+='<label class="tg" style="margin-left:8px;vertical-align:middle"><input type="checkbox" '+(v.enabled?'checked':'')+' onchange="tglOt(\''+v.name.replace(/'/g,"\\'")+'\',this.checked)"><span class="sl"></span></label>';h+='<span style="color:var(--m);font-size:10px;margin-left:6px">'+(v.enabled?'启用':'禁用')+'</span>';if(v.note)h+='<div style="color:var(--m);font-size:11px;margin-top:2px">📝 '+v.note+'</div>';h+='<div style="margin-top:4px"><span style="color:var(--w);font-size:11px">玩家: </span><code style="font-size:12px">'+v.player+'</code>';h+=' <span class="badge">'+(v.match_type==='exact'?'精确匹配':'包含匹配')+'</span>';h+=' <span style="color:var(--w);font-size:11px">冷却: </span>'+v.cooldown_seconds+'秒</div>';h+='<pre style="margin:6px 0 0;font-size:11px;color:var(--s)">'+(v.commands||[]).join("\n")+'</pre></div>';h+='<div class="ac"><button class="bw bsm" onclick="edOt(\''+v.name.replace(/'/g,"\\'")+'\','+i+')">编辑</button><button class="bd bsm" onclick="rmOt(\''+v.name.replace(/'/g,"\\'")+'\')">删除</button></div></div></div>'}}document.getElementById("main").innerHTML=h;window._otriggers=t;window._ccCmds=cc}
function adSc(){document.body.insertAdjacentHTML("beforeend",'<div class="mbg" id="sc-m" onclick="if(event.target===this)this.remove()"><div class="mod"><h3>新建/覆盖脚本</h3><div class="fg"><label>文件名</label><input id="sfn2"></div><div class="fg"><label>脚本内容(一行一条命令)</label><textarea id="sct" rows="8"></textarea></div><div class="fr" style="margin-top:14px"><button class="b1 bs" onclick="doSc()">保存</button><button class="b2 bs" onclick="document.getElementById(\'sc-m\').remove()">取消</button></div></div></div>')}
async function doSc(){var n=document.getElementById("sfn2").value.trim(),c=document.getElementById("sct").value;if(!n){toast("请输入文件名",true);return}await pj(A+"/scripts",{name:n,content:c});document.getElementById("sc-m")?.remove();toast("脚本已保存");loSc()}
async function rmSc(n){if(!confirm("确定要删除脚本 '"+n+"'吗？"))return;await fetch(A+"/scripts/"+encodeURIComponent(n),{method:"DELETE"});toast("脚本已删除");loSc()}
async function tglSc(name,enabled){try{await pjt(A+"/scripts/"+encodeURIComponent(name),{enabled:enabled});toast(enabled?"已启用":"已禁用")}catch(e){toast(e.message,true)}}
/* ====== 自定义命令映射 ====== */
function addCc(){var gid=window._ccGid;if(!gid){toast("请先选择群聊",true);return}document.body.insertAdjacentHTML("beforeend",'<div class="mbg" id="cc-m" onclick="if(event.target===this)this.remove()"><div class="mod" style="max-width:560px"><h3>添加自定义命令</h3><div class="fg"><label>命令别名 *</label><input id="cca" placeholder="如：苹果"><div style="font-size:10px;color:var(--m);margin-top:2px">使用 /rc自定 &lt;别名&gt; 触发</div></div><div class="fg"><label>RCON命令 *</label><textarea id="ccr" rows="3" placeholder="如：give Aphqsia apple 1"></textarea></div><div class="fg"><label>描述（可选）</label><input id="ccd" placeholder="给Aphqsia一个苹果"></div><div class="fg"><label>白名单QQ（可选，逗号分隔）</label><input id="ccw" placeholder="留空则使用全局权限"></div><div class="fg"><label class="tg"><input type="checkbox" id="ccsr" checked><span class="sl"></span> 返回服务器回复</label></div><div style="margin-top:14px"><button class="b1 bs" onclick="saveCc(-1)">保存</button><button class="b2 bs" onclick="document.getElementById(\'cc-m\').remove()">取消</button></div></div></div>')}
function edCc(idx){var cmds=window._ccCmds||[];var v=cmds[idx];if(!v)return;document.body.insertAdjacentHTML("beforeend",'<div class="mbg" id="cc-m" onclick="if(event.target===this)this.remove()"><div class="mod" style="max-width:560px"><h3>编辑自定义命令</h3><div class="fg"><label>命令别名 *</label><input id="cca" value="'+v.alias+'"></div><div class="fg"><label>RCON命令 *</label><textarea id="ccr" rows="3">'+v.rcon_cmd+'</textarea></div><div class="fg"><label>描述（可选）</label><input id="ccd" value="'+(v.description||'')+'"></div><div class="fg"><label>白名单QQ（可选，逗号分隔）</label><input id="ccw" value="'+(v.whitelist||[]).join(', ')+'"></div><div class="fg"><label class="tg"><input type="checkbox" id="ccsr" '+(v.show_reply!==false?'checked':'')+'><span class="sl"></span> 返回服务器回复</label></div><div style="margin-top:14px"><button class="b1 bs" onclick="saveCc('+idx+')">保存</button><button class="b2 bs" onclick="document.getElementById(\'cc-m\').remove()">取消</button></div></div></div>')}
async function saveCc(idx){var gid=window._ccGid;if(!gid)return;var a=document.getElementById("cca").value.trim(),r=document.getElementById("ccr").value.trim(),d=document.getElementById("ccd").value.trim(),w=(document.getElementById("ccw").value||"").split(",").map(function(s){return s.trim()}).filter(Boolean),sr=document.getElementById("ccsr").checked;if(!a||!r){toast("别名和RCON命令不能为空",true);return}var data={alias:a,rcon_cmd:r,description:d,whitelist:w,show_reply:sr};if(idx>=0){await pjt(A+"/custom-cmds/"+gid+"/"+idx,data)}else{await pj(A+"/custom-cmds",Object.assign({gid:gid},data))}document.getElementById("cc-m")?.remove();toast(idx>=0?"已更新":"已添加");loSc()}
async function delCc(idx){if(!confirm("确定要删除此自定义命令吗？"))return;var gid=window._ccGid;if(!gid)return;await fetch(A+"/custom-cmds/"+gid+"/"+idx,{method:"DELETE"});toast("已删除");loSc()}
async function tglCc(idx,enabled){var gid=window._ccGid;if(!gid)return;await pjt(A+"/custom-cmds/"+gid+"/"+idx,{enabled:enabled})}
async function tglCcReply(idx,enabled){var gid=window._ccGid;if(!gid)return;await pjt(A+"/custom-cmds/"+gid+"/"+idx,{show_reply:enabled})}

async function adEm(idx){var em=window._emacros||[],v=idx!==undefined?em[idx]:null;var etOpts='<option value="player_first_join">玩家首次加入</option><option value="player_join">玩家加入</option><option value="player_leave">玩家退出</option><option value="player_kick">玩家被踢出</option><option value="player_death_pvp">玩家被击杀(PVP)</option><option value="player_death">玩家死亡</option><option value="player_first_death">玩家首次死亡</option><option value="player_respawn">玩家复活</option><option value="player_advancement">玩家成就</option><option value="player_chat">玩家发言</option><option value="player_item_get">玩家获得物品</option><option value="server_start">服务器启动</option><option value="server_stop">服务器关闭</option><option value="server_reload">服务器重载</option><option value="tps_low">TPS低告警</option><option value="tps_critical">TPS严重告警</option><option value="memory_high">内存高占用</option><option value="server_perf_issue">综合性能异常</option><option value="admin_join">👑 管理员加入</option><option value="vip_join">💎 VIP加入</option><option value="vip_leave">💎 VIP退出</option><option value="vip_death">💎 VIP死亡</option><option value="boss_kill">Boss击杀</option><option value="player_online_duration">⏱ 在线时长</option>';var _em_etNames={player_first_join:'首次加入',player_join:'加入',player_leave:'退出',player_kick:'被踢',player_death_pvp:'PVP击杀',player_death:'死亡',player_first_death:'首次死亡',player_respawn:'复活',player_advancement:'成就',player_item_get:'物品',server_start:'启动',server_stop:'关闭',server_reload:'重载',boss_kill:'Boss击杀',player_chat:'发言',tps_low:'TPS低',tps_critical:'TPS严重',memory_high:'内存高',server_perf_issue:'性能异常',admin_join:'管理员加入',vip_join:'VIP加入',vip_leave:'VIP退出',vip_death:'VIP死亡',player_online_duration:'在线时长'};window._em_etId=0;window._em_etOpts=etOpts;_em_ets=(function(){var arr=[];var raw=v&&v.event_types?v.event_types:(v&&v.event_type?[v.event_type]:[""]);for(var ei=0;ei<raw.length;ei++){var et=raw[ei];if(typeof et==='object'&&et){arr.push({_i:ei,val:et.type||et.val||"",preDelay:parseFloat(et.pre_delay)||0,postDelay:parseFloat(et.post_delay)||0,cmds:et.commands||[],durMin:parseInt(et.duration_minutes)||0,durMode:et.duration_mode||'session',durWinHrs:parseInt(et.duration_window_hours)||24,vipLevel:parseInt(et.vip_level)||0})}else{arr.push({_i:ei,val:et||"",preDelay:0,postDelay:0,cmds:[],durMin:0,durMode:'session',durWinHrs:24,vipLevel:0})}}return arr})();_em_conds=v&&v.conditions?v.conditions.slice():[];var srvOpts='<option value="">-- 选择服务器 --</option>';try{var g=await fj(A+"/groups?filter_web_mgmt=1");var seen={};for(var gid in g){var srvs=g[gid]||[];for(var i=0;i<srvs.length;i++){var s=srvs[i];var sn=s.server_name||s.name||'';if(sn&&!seen[sn]){seen[sn]=true;srvOpts+='<option value="'+sn+'"'+(v&&v.server_name===sn?" selected":"")+'>'+sn+'</option>'}}}}catch(e){}var plOpts='<option value="">-- 不限 --</option>';try{var pl=await fj(A+"/players");if(pl&&pl.length){var seenMc={};for(var pi=0;pi<pl.length;pi++){var mc=pl[pi].mc_id;if(mc&&!seenMc[mc]){seenMc[mc]=true;plOpts+='<option value="'+mc+'"'+(v&&v.player_name===mc?" selected":"")+'>'+mc+'</option>'}}}}catch(e){}window._plOpts=plOpts;var h='<div class="mbg" id="em-m" onclick="if(event.target===this)this.remove()"><div class="mod" style="max-width:620px"><h3>'+(v?"编辑":"新建")+'事件宏</h3><div class="fg"><label>名称 *</label><input id="emn" value="'+(v?v.name:"")+'"></div><div class="fg"><label>事件类型 <span style="color:var(--w);font-size:10px">💡 用+添加多种事件（任一触发）</span></label><div id="em-ets">'+(function(){var r='';for(var ei=0;ei<_em_ets.length;ei++){var e=_em_ets[ei];r+=emEtRow(ei,e.val,e.preDelay,e.postDelay,e.cmds,e.durMin,e.durMode,e.durWinHrs,e.vipLevel)}return r})()+'</div><button class="bw bsm" onclick="emEtAdd()" style="font-size:10px;padding:1px 8px;margin-bottom:6px">+ 添加事件类型</button></div><div class="fg"><label>目标服务器 *</label><select id="emsn">'+srvOpts+'</select></div><div class="fg"><label>限定玩家（可选）</label><select id="empl">'+plOpts+'</select></div><div class="fg"><label>逻辑门模式 <span style="color:var(--w);font-size:10px" title="决定多个条件如何组合: AND=全部满足才触发, OR=任一满足即触发">💡</span></label><select id="emgate" onchange="_gate_mode=this.value"><option value="and"'+(v&&v.gate_mode!=="or"?" selected":"")+'>与门 AND（全部满足）</option><option value="or"'+(v&&v.gate_mode==="or"?" selected":"")+'>或门 OR（任一满足）</option></select></div><div class="fg"><label>执行条件（可选）<span style="color:var(--m);font-size:10px">用+添加条件，配合上方逻辑门</span></label><div id="em-conds">'+(function(){var r='';if(v&&v.conditions&&v.conditions.length){for(var ci=0;ci<v.conditions.length;ci++){var c=v.conditions[ci];r+=emCondRow(ci,c.type,c.value,c.not)}}return r})()+'</div><button class="bw bsm" onclick="emCondAdd()" style="font-size:10px;padding:1px 8px;margin-bottom:6px">+ 添加条件</button></div><div class="fg"><label title="全局RCON命令。若上方事件类型配置了前/后延时的独立命令，则使用独立命令；若事件类型未配置命令，则使用此全局命令">RCON命令（全局）</label><textarea id="emcmds" rows="3" placeholder="say {player} 死了！&#10;give {player} apple 1">'+(v?(v.commands||[]).join("\n"):"")+'</textarea></div><div class="fg"><label>事件参数（可选）<span style="color:var(--m);font-size:10px">匹配日志内容/物品/Boss名/性能关键词（通过服务器日志检测，非RCON）</span></label><textarea id="empar" rows="1" placeholder="如：diamond_sword / ender_dragon">'+(v?v.event_param||"":"")+'</textarea></div><div class="fg"><label>QQ通知消息（可选，支持变量：{player} {server} {event_type} {event_param}）</label><textarea id="emqq" rows="2" placeholder="如：我们有新玩家 {player} 加入啦！">'+(v?v.qq_message||"":"")+'</textarea></div><div class="fr"><div class="fg"><label title="在指定窗口内最多触发次数，配合窗口使用。0=不限">频率限制（次）<span style="color:var(--w);font-size:10px">💡</span></label><input id="emmax" type="number" value="'+(v?v.max_triggers||0:0)+'" min="0" step="1" style="width:80px"></div><div class="fg"><label title="频率限制统计窗口。例: 5次/60秒=每分钟最多5次">窗口（秒）<span style="color:var(--w);font-size:10px">💡</span></label><input id="emwin" type="number" value="'+(v?v.trigger_window||0:0)+'" min="0" step="1" style="width:80px"></div></div><div class="fr"><div class="fg"><label class="tg" title="关闭后此事件宏不执行"><input type="checkbox" id="emen" '+(v&&v.enabled?"checked":"")+'><span class="sl"></span> 启用</label></div><div class="fg"><label title="两次触发之间的最小间隔秒数。0=无冷却">冷却时间（秒）<span style="color:var(--w);font-size:10px">💡</span></label><input id="emcd" type="number" value="'+(v?v.cooldown||0:0)+'" min="0" step="1" style="width:80px"></div></div><div style="margin-top:14px"><button class="b1 bs" onclick="doEmSave('+idx+')">保存</button><button class="b2 bs" onclick="document.getElementById(\'em-m\').remove()">取消</button></div></div></div>';_gate_mode=v&&v.gate_mode?v.gate_mode:"and";document.body.insertAdjacentHTML("beforeend",h)}var _gate_mode="and";var _em_ets=[];var _em_conds=[];var _em_condId=0;var _em_etId=0;var _em_etOpts='';function emEtRow(i,val,preDelay,postDelay,cmds,durMin,durMode,durWinHrs,vipLevel){preDelay=parseFloat(preDelay)||0;postDelay=parseFloat(postDelay)||0;cmds=cmds||[];durMin=parseInt(durMin)||0;durMode=durMode||'session';durWinHrs=parseInt(durWinHrs)||24;vipLevel=parseInt(vipLevel)||0;var isDur=val==='player_online_duration';var isVip=val&&(val==='vip_join'||val==='vip_leave'||val==='vip_death');var opts=window._em_etOpts||"";if(val){opts=opts.replace("value=\""+val+"\"","value=\""+val+"\" selected")}var hasDelay=(preDelay>0||postDelay>0||isDur||isVip);return '<div class="fr" style="margin-bottom:3px;gap:4px;flex-wrap:wrap" id="emetr'+i+'"><select onchange="emEtChg('+i+',this.value)" style="flex:1;min-width:100px;font-size:11px"><option value="">-- 选择事件 --</option>'+opts+'</select><input type="number" value="'+preDelay+'" min="0" step="0.5" style="width:44px;font-size:10px;padding:1px 2px" title="前延时(秒)" placeholder="前" onchange="emEtPreDelay('+i+',this.value)"><span style="font-size:9px;color:var(--m)">前</span><input type="number" value="'+postDelay+'" min="0" step="0.5" style="width:44px;font-size:10px;padding:1px 2px" title="后延时(秒)" placeholder="后" onchange="emEtPostDelay('+i+',this.value)"><span style="font-size:9px;color:var(--m)">后</span><button class="bd bsm" onclick="emEtDel('+i+')" style="padding:1px 4px;font-size:9px">x</button><div id="emetvip'+i+'" style="width:100%;display:'+(isVip?'flex':'none')+';gap:4px;align-items:center;flex-wrap:wrap;margin-top:2px;background:var(--bg2);padding:6px;border-radius:4px"><span style="font-size:10px;color:var(--s)">💎 VIP等级</span><select onchange="emEtVipLevel('+i+',this.value)" style="font-size:10px;padding:2px"><option value="0"'+(vipLevel===0?' selected':'')+'>所有VIP</option><option value="1"'+(vipLevel===1?' selected':'')+'>等级 1</option><option value="2"'+(vipLevel===2?' selected':'')+'>等级 2</option><option value="3"'+(vipLevel===3?' selected':'')+'>等级 3</option><option value="4"'+(vipLevel===4?' selected':'')+'>等级 4</option><option value="5"'+(vipLevel===5?' selected':'')+'>等级 5</option></select></div><div id="emetdur'+i+'" style="width:100%;display:'+(isDur?'flex':'none')+';gap:4px;align-items:center;flex-wrap:wrap;margin-top:2px;background:var(--bg2);padding:6px;border-radius:4px"><span style="font-size:10px;color:var(--a)">⏱ 在线</span><input type="number" value="'+durMin+'" min="1" step="1" style="width:50px;font-size:10px;padding:2px" title="在线时长阈值(分钟)" onchange="emEtDurMin('+i+',this.value)"><span style="font-size:10px;color:var(--m)">分钟</span><select onchange="emEtDurMode('+i+',this.value)" style="font-size:10px;padding:2px"><option value="session"'+('session'===durMode?' selected':'')+'>单次登录</option><option value="cumulative"'+('cumulative'===durMode?' selected':'')+'>累计时长</option></select><span id="emetdurwin'+i+'" style="font-size:10px;color:var(--m);display:'+('cumulative'===durMode?'inline':'none')+'">近 <input type="number" value="'+durWinHrs+'" min="1" step="1" style="width:42px;font-size:10px;padding:2px" title="累计统计窗口(小时)" onchange="emEtDurWin('+i+',this.value)"> 小时内</span></div><div id="emetc'+i+'" style="width:100%;margin-top:2px;display:'+(hasDelay?'block':'none')+'"><div style="font-size:10px;color:var(--m);margin-bottom:3px">独立RCON命令 <button onclick="emEtCmdAdd('+i+')" style="padding:0 4px;font-size:9px;margin-left:4px">+ 添加</button></div><div id="emetcl'+i+'">'+(function(){var r='';for(var ci=0;ci<cmds.length;ci++){var c=cmds[ci],cmd='',dly=0;if(typeof c==='object'){cmd=c.cmd||'';dly=parseFloat(c.delay)||0}else{cmd=c||''}r+='<div class="fr" style="margin-bottom:2px;gap:3px" id="emetcr'+i+'_'+ci+'"><input value="'+cmd.replace(/"/g,'&quot;')+'" onchange="emEtCmdChg('+i+','+ci+',\'cmd\',this.value)" placeholder="RCON命令" style="flex:1;font-size:10px;padding:2px 4px"><input type="number" value="'+dly+'" min="0" step="0.5" onchange="emEtCmdChg('+i+','+ci+',\'delay\',this.value)" title="此命令执行前等待(秒)" style="width:42px;font-size:10px;padding:2px"><button class="bd bsm" onclick="emEtCmdDel('+i+','+ci+')" style="padding:1px 3px;font-size:9px">x</button></div>'}return r})()+'</div></div></div>'}function emEtAdd(){var i=_em_etId++;var dftE=_em_ets.length>0?_em_ets[_em_ets.length-1]:null;var dft=dftE?dftE.val||"":"";_em_ets.push({_i:i,val:dft,preDelay:0,postDelay:0,cmds:[],durMin:0,durMode:'session',durWinHrs:24,vipLevel:0});var c=document.getElementById("em-ets");if(c)c.insertAdjacentHTML("beforeend",emEtRow(i,dft,0,0,[],0,'session',24,0))}function emEtDel(i){for(var j=0;j<_em_ets.length;j++)if(_em_ets[j]._i==i){_em_ets.splice(j,1);break}var e=document.getElementById("emetr"+i);if(e)e.remove()}function emEtChg(i,v){for(var j=0;j<_em_ets.length;j++)if(_em_ets[j]._i==i){_em_ets[j].val=v;var isDur=v==='player_online_duration',isVip=v=='vip_join'||v=='vip_leave'||v=='vip_death';var edur=document.getElementById('emetdur'+i),evip=document.getElementById('emetvip'+i),ecmds=document.getElementById('emetc'+i);if(edur)edur.style.display=isDur?'flex':'none';if(evip)evip.style.display=isVip?'flex':'none';if(ecmds&&!isDur){var et=_em_ets[j];var pre=parseFloat(et&&et.preDelay)||0,post=parseFloat(et&&et.postDelay)||0;ecmds.style.display=(pre>0||post>0)?'block':'none'}else if(ecmds&&isDur)ecmds.style.display='block';break}}function emEtPreDelay(i,v){for(var j=0;j<_em_ets.length;j++)if(_em_ets[j]._i==i){_em_ets[j].preDelay=parseFloat(v)||0;break}emEtToggleCmds(i)}function emEtPostDelay(i,v){for(var j=0;j<_em_ets.length;j++)if(_em_ets[j]._i==i){_em_ets[j].postDelay=parseFloat(v)||0;break}emEtToggleCmds(i)}function emEtCmdAdd(i){for(var j=0;j<_em_ets.length;j++)if(_em_ets[j]._i==i){if(!_em_ets[j].cmds)_em_ets[j].cmds=[];_em_ets[j].cmds.push({cmd:'',delay:0});var ci=_em_ets[j].cmds.length-1;var el=document.getElementById('emetcl'+i);if(el)el.insertAdjacentHTML('beforeend','<div class="fr" style="margin-bottom:2px;gap:3px" id="emetcr'+i+'_'+ci+'"><input onchange="emEtCmdChg('+i+','+ci+',\'cmd\',this.value)" placeholder="RCON命令" style="flex:1;font-size:10px;padding:2px 4px"><input type="number" value="0" min="0" step="0.5" onchange="emEtCmdChg('+i+','+ci+',\'delay\',this.value)" title="此命令执行前等待(秒)" style="width:42px;font-size:10px;padding:2px"><button class="bd bsm" onclick="emEtCmdDel('+i+','+ci+')" style="padding:1px 3px;font-size:9px">x</button></div>');break}}function emEtCmdDel(i,ci){for(var j=0;j<_em_ets.length;j++)if(_em_ets[j]._i==i){if(_em_ets[j].cmds)_em_ets[j].cmds.splice(ci,1);break}var el=document.getElementById('emetcr'+i+'_'+ci);if(el)el.remove()}function emEtCmdChg(i,ci,field,val){for(var j=0;j<_em_ets.length;j++)if(_em_ets[j]._i==i){if(!_em_ets[j].cmds)_em_ets[j].cmds=[];if(!_em_ets[j].cmds[ci]||typeof _em_ets[j].cmds[ci]!=='object'){var oldCmd=typeof _em_ets[j].cmds[ci]==='string'?_em_ets[j].cmds[ci]:'';_em_ets[j].cmds[ci]={cmd:oldCmd,delay:0}}if(field==='delay')_em_ets[j].cmds[ci].delay=parseFloat(val)||0;else _em_ets[j].cmds[ci].cmd=val;break}}function emEtToggleCmds(i){var et=null;for(var j=0;j<_em_ets.length;j++)if(_em_ets[j]._i==i){et=_em_ets[j];break}var pre=parseFloat(et&&et.preDelay)||0,post=parseFloat(et&&et.postDelay)||0;var el=document.getElementById('emetc'+i);if(el)el.style.display=(pre>0||post>0)?'block':'none'}function emEtDurMin(i,v){for(var j=0;j<_em_ets.length;j++)if(_em_ets[j]._i==i){_em_ets[j].durMin=parseInt(v)||0;break}}function emEtDurMode(i,v){for(var j=0;j<_em_ets.length;j++)if(_em_ets[j]._i==i){_em_ets[j].durMode=v;var el=document.getElementById('emetdurwin'+i);if(el)el.style.display=v==='cumulative'?'inline':'none';break}}function emEtDurWin(i,v){for(var j=0;j<_em_ets.length;j++)if(_em_ets[j]._i==i){_em_ets[j].durWinHrs=parseInt(v)||1;break}}function emEtVipLevel(i,v){for(var j=0;j<_em_ets.length;j++)if(_em_ets[j]._i==i){_em_ets[j].vipLevel=parseInt(v)||0;break}}function emCondRow(i,type,val,not){type=type||"player";val=val||"";not=!!not;var vpart="";if(type==="player"){vpart='<select onchange="emCondVal('+i+',this.value)" style="flex:1;font-size:10px">'+(window._plOpts||'')+'</select>'}else{vpart='<input value="'+val+'" onchange="emCondVal('+i+',this.value)" placeholder="匹配日志行内容，不区分大小写" style="flex:1;font-size:10px">'}return '<div class="fr" style="margin-bottom:3px;gap:4px" id="emcr'+i+'"><select onchange="emCondChg('+i+',this.value)" style="width:65px;font-size:10px"><option value="player"'+(type=="player"?" selected":"")+'>玩家</option><option value="content"'+(type=="content"?" selected":"")+'>内容</option></select>'+vpart+'<label style="display:flex;align-items:center;gap:2px;font-size:10px;white-space:nowrap;cursor:pointer" title="非门：反转此条件"><input type="checkbox" '+(not?'checked':'')+' onchange="emCondNot('+i+',this.checked)" style="width:14px;height:14px;cursor:pointer">非</label><button class="bd bsm" onclick="emCondDel('+i+')" style="padding:1px 4px;font-size:9px">x</button></div>'}function emCondAdd(){var i=_em_condId++;_em_conds.push({type:"player",value:"",not:false});var c=document.getElementById("em-conds");if(c)c.insertAdjacentHTML("beforeend",emCondRow(i,"player","",false))}function emCondDel(i){for(var j=0;j<_em_conds.length;j++)if(_em_conds[j]._i==i){_em_conds.splice(j,1);break}var e=document.getElementById("emcr"+i);if(e)e.remove()}function emCondChg(i,v){for(var j=0;j<_em_conds.length;j++)if(_em_conds[j]._i==i){_em_conds[j].type=v;_em_conds[j].value="";break}var e=document.getElementById("emcr"+i);if(e){var d=document.createElement("div");d.innerHTML=emCondRow(i,v,"",false);var ne=d.firstChild;ne.id="emcr"+i;e.parentNode.replaceChild(ne,e)}}function emCondVal(i,v){for(var j=0;j<_em_conds.length;j++)if(_em_conds[j]._i==i){_em_conds[j].value=v;break}}function emCondNot(i,v){for(var j=0;j<_em_conds.length;j++)if(_em_conds[j]._i==i){_em_conds[j].not=v;break}}
function edEm(idx){adEm(idx)}
async function delEm(idx){if(!confirm("确定要删除此事件宏吗？"))return;await fetch(A+"/event-macros/"+idx,{method:"DELETE"});toast("已删除");loMa()}
async function tglEm(idx,enabled){await pjt(A+"/event-macros/"+idx,{enabled:enabled});toast(enabled?"已启用":"已禁用");loMa()}
async function expEm(){var em=window._emacros||[];var blob=new Blob([JSON.stringify(em,null,2)],{type:"application/json"});var a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download="event_macros.json";a.click();toast("已导出 "+em.length+" 个事件宏")}
async function impEm(){var inp=document.createElement("input");inp.type="file";inp.accept=".json";inp.onchange=async function(e){var f=e.target.files[0];if(!f)return;var t=await f.text();var r=await (await fetch(A+"/event-macros/import",{method:"POST",headers:{"Content-Type":"application/json"},body:t})).json();if(r.ok!==false){toast("导入了 "+r.imported+" 个事件宏");loMa()}else{toast(r.error||"导入失败",true)}};inp.click()}
async function doEmSave(idx){var b={name:document.getElementById("emn").value.trim(),event_types:_em_ets.map(function(et){return{type:et.val||"",pre_delay:parseFloat(et.preDelay)||0,post_delay:parseFloat(et.postDelay)||0,commands:(et.cmds||[]).map(function(c){if(typeof c==='object')return c;return{cmd:c||'',delay:0}}),duration_minutes:parseInt(et.durMin)||0,duration_mode:et.durMode||'session',duration_window_hours:parseInt(et.durWinHrs)||24,vip_level:parseInt(et.vipLevel)||0}}).filter(function(et){return et.type}),server_name:document.getElementById("emsn").value.trim(),commands:document.getElementById("emcmds").value.split("\n").map(function(s){return s.trim()}).filter(Boolean),enabled:document.getElementById("emen").checked,cooldown:parseFloat(document.getElementById("emcd").value)||0,player_name:document.getElementById("empl").value.trim(),max_triggers:parseInt(document.getElementById("emmax").value)||0,trigger_window:parseInt(document.getElementById("emwin").value)||0,event_param:document.getElementById("empar").value.trim(),qq_message:document.getElementById("emqq").value.trim(),gate_mode:_gate_mode||"and",conditions:_em_conds.map(function(c){return{type:c.type||"player",value:c.value||"",not:!!c.not}})};if(!b.name||!b.server_name){toast("请填写名称和目标服务器",true);return}if(idx!==undefined&&idx>=0){await pjt(A+"/event-macros/"+idx,b)}else{await pj(A+"/event-macros",b)}document.getElementById("em-m")?.remove();toast("保存成功");loMa()}
/* ====== 日志查看器 ====== */
var _lv_type="",_lv_server="",_lv_player="";
async function loLogViewer(){try{var srvs=await fj(A+"/log-viewer/servers");var lv=await doLvFetch();var cfg={};try{cfg=await fj(A+"/config/all")}catch(e){}var h='';h+='<div class="fb" style="margin-bottom:12px"><h3 style="margin:0">📄 日志查看器</h3><button class="b1 bsm" onclick="refLog()" style="margin-left:auto" title="手动刷新">🔄 刷新</button></div>';h+='<div class="ct" style="padding:14px"><div class="fr" style="gap:16px;align-items:center;flex-wrap:wrap;margin-bottom:14px"><select id="lv-srv" onchange="lvSrvChange(this.value)" style="padding:4px 8px"><option value="">全部服务器</option>';if(srvs&&srvs.length)srvs.forEach(function(s){h+='<option value="'+s.name+'" '+(_lv_server===s.name?'selected':'')+'>'+s.name+'</option>'});h+='</select><div style="display:flex;align-items:center;gap:8px;margin-left:auto"><span style="font-size:11px;color:var(--a)">⏱ 间隔</span><input id="lv-refresh-ms" type="number" value="'+(cfg.log_viewer_refresh_ms||10000)+'" min="0" step="1000" style="width:72px;text-align:center;padding:3px 4px" title="0=关闭自动刷新。⚠ &lt;3000ms会导致控制台大量刷屏"><span style="font-size:10px;color:var(--m)">ms</span><span style="font-size:10px;color:#e74c3c;margin-left:2px" title="刷新间隔过短会导致控制台日志大量输出">⚠ &lt;3000=刷屏</span><button class="b2 bsm" onclick="tglLogRefresh()">应用</button></div></div>';h+='<details style="margin-bottom:12px;font-size:12px"><summary style="cursor:pointer;color:var(--a)">🔧 分类模式 (JSON)</summary><div style="margin-top:6px"><textarea id="lv-log-patterns" rows="4" style="width:100%;max-width:550px;font-size:11px">'+JSON.stringify(cfg.log_patterns||{}).replace(/"/g,"&quot;")+'</textarea><div style="margin-top:6px"><button class="b1 bsm" onclick="saveLogPatterns()">💾 保存分类模式</button><span style="font-size:10px;color:var(--m);margin-left:8px">key=分类名 value=正则 留空使用默认 保存后即时生效</span></div></div></details>';var curSrv=null,curMode='file',curPaths=[],curFolder='',curFPattern='latest.log';if(_lv_server){for(var i=0;i<srvs.length;i++){if(srvs[i].name===_lv_server){curSrv=srvs[i];curMode=srvs[i].log_mode||'file';curPaths=srvs[i].log_paths||[];curFolder=srvs[i].log_folder||'';curFPattern=srvs[i].log_file_pattern||'latest.log';break}}}h+='<div style="padding-top:12px;border-top:1px solid var(--b)"><div class="fr" style="gap:14px;align-items:center;margin-bottom:8px;flex-wrap:wrap"><span style="font-size:13px;font-weight:600;white-space:nowrap">📁 日志路径</span><span style="font-size:10px;color:#e74c3c;margin-left:8px;white-space:nowrap">⚠ Docker中MC在另一容器时需先配置卷挂载才能读取日志文件</span><label style="display:flex;align-items:center;gap:5px;cursor:pointer;font-size:12px;white-space:nowrap"><input type="radio" name="lv-mode" value="file" '+(curMode==='file'?'checked':'')+' onchange="lvModeChange(this.value)" id="lv-mode-file"> 文件模式</label><label style="display:flex;align-items:center;gap:5px;cursor:pointer;font-size:12px;white-space:nowrap"><input type="radio" name="lv-mode" value="folder" '+(curMode==='folder'?'checked':'')+' onchange="lvModeChange(this.value)" id="lv-mode-folder"> 文件夹模式</label><button class="b1 bsm" onclick="saveLogPath()" style="margin-left:4px">💾 保存</button><button class="bw bsm" onclick="testLogFile()" style="margin-left:4px" title="读取日志最后100行检测可读性">🔍 检测</button></div><div id="lv-file-section" style="display:'+(curMode==='folder'?'none':'block')+'"><textarea id="lv-logpaths" placeholder="一行一个日志文件路径&#10;如 D:/mc/logs/latest.log" rows="3" style="width:100%;max-width:550px;font-size:11px">'+escapeHtml(curPaths.join('\n'))+'</textarea></div><div id="lv-folder-section" style="display:'+(curMode==='folder'?'block':'none')+'"><div class="fr" style="gap:8px"><input id="lv-logfolder" placeholder="文件夹路径，如 D:/mc/logs" value="'+escapeHtml(curFolder)+'" style="flex:1;max-width:390px;font-size:11px"><input id="lv-logfpattern" placeholder="文件名，如 latest.log" value="'+escapeHtml(curFPattern)+'" style="width:160px;font-size:11px"></div></div></div></div>';h+='<div class="fb" style="margin-top:10px;gap:8px;flex-wrap:wrap;align-items:center"><div id="lv-tabs" style="display:flex;gap:4px;flex-wrap:wrap">';var tabs=[["","全部"],["chat","💬聊天"],["command","⌨️命令"],["player_death","💀死亡"],["player_join,player_leave","🚪进出"],["player_advancement","⭐成就"],["system","⚙️系统"],["other","📎其他"]];tabs.forEach(function(t){h+='<button class="b'+(_lv_type===t[0]?'1':'2')+' bsm" onclick="_lv_type=\''+t[0]+'\';loLogViewer()">'+t[1]+'</button>'});h+='</div><input id="lv-player" value="'+_lv_player+'" placeholder="👤 玩家筛选" onchange="_lv_player=this.value;loLogViewer()" style="width:120px;margin-left:auto"></div>';h+='<div class="ct" style="margin-top:8px" id="lv-list">'+buildLvList(lv)+'</div>';document.getElementById("main").innerHTML=h;document.getElementById("lv-srv").value=_lv_server;refresh(cfg.log_viewer_refresh_ms||10000,async function(){var l=await doLvFetch();var el=document.getElementById("lv-list");if(el)el.innerHTML=buildLvList(l)})}catch(e){document.getElementById("main").innerHTML='<div class="ct"><h3>📄 日志查看器</h3><div class="emp">加载失败: '+e.message+'<br><small>请确认已配置服务器日志路径</small></div></div>'}}function lvSrvChange(v){_lv_server=v;loLogViewer()}function lvModeChange(v){document.getElementById("lv-file-section").style.display=v==="file"?"block":"none";document.getElementById("lv-folder-section").style.display=v==="folder"?"block":"none"}async function saveLogPath(){if(!_lv_server){toast("请先选择服务器",true);return}var mode=document.getElementById("lv-mode-file").checked?"file":"folder";var data={server_name:_lv_server,log_mode:mode};if(mode==="file"){var txt=document.getElementById("lv-logpaths").value;data.log_paths=txt.split("\n").map(function(s){return s.trim()}).filter(Boolean)}else{data.log_folder=document.getElementById("lv-logfolder").value.trim();data.log_file_pattern=document.getElementById("lv-logfpattern").value.trim()||"latest.log"}try{var r=await pjt(A+"/log-viewer/log-path",data);toast("已保存，更新了 "+r.updated+" 个服务器配置")}catch(e){toast("保存失败: "+e.message,true)}}async function tglLogRefresh(){var v=parseInt(document.getElementById("lv-refresh-ms").value)||10000;try{await pjt(A+"/config/save",{log_viewer_refresh_ms:v});toast("已设为 "+v+"ms，重新进入生效")}catch(e){toast("保存失败: "+e.message,true)}}
async function saveLogPatterns(){try{var v=document.getElementById("lv-log-patterns").value;var lp={};try{lp=JSON.parse(v)}catch(e){toast("JSON 格式错误: "+e.message,true);return}await pjt(A+"/config/save",{log_patterns:lp});toast("分类模式已保存，即时生效")}catch(e){toast("保存失败: "+e.message,true)}}
async function doLvFetch(){var p=["limit=300"];if(_lv_type)p.push("types="+_lv_type);if(_lv_server)p.push("server="+encodeURIComponent(_lv_server));if(_lv_player)p.push("player="+encodeURIComponent(_lv_player));var r=await fj(A+"/log-viewer/recent?"+p.join("&"));return Array.isArray(r)?r:[]}
function buildLvList(data){if(!data||!data.length)return'<div class="emp">暂无日志（确认已在服务器管理中填写日志路径）</div>';var rows='<table style="width:100%;font-size:12px"><tr style="position:sticky;top:0;background:var(--bg)"><th style="width:85px">时间</th><th style="width:90px">服务器</th><th style="width:60px">类型</th><th style="width:80px">玩家</th><th>内容</th></tr>';data.forEach(function(e){var tb={chat:"badge",command:"badge",player_death:"badge",player_join:"badge",player_leave:"badge",player_advancement:"badge",system:"badge"};var tl={chat:"💬",command:"⌨️",player_death:"💀",player_join:"▶","player_leave":"◀",player_advancement:"⭐",system:"⚙️",other:"📎"};var d=new Date(e.ts*1000),ts=d.toTimeString().slice(0,8);rows+='<tr><td style="color:var(--m);white-space:nowrap">'+ts+'</td><td style="white-space:nowrap;color:var(--a)">'+e.server+'</td><td><span class="'+tb[e.type]+'">'+(tl[e.type]||"📎")+' '+e.type+'</span></td><td style="white-space:nowrap">'+(e.player||"-")+'</td><td style="color:var(--m);word-break:break-all">'+escapeHtml(e.text)+'</td></tr>'});rows+='</table>';return rows}
/* ====== 快捷命令 ====== */
async function loCmd(){
    var g=await fj(A+"/groups?filter_web_mgmt=1"),
        qcs=await fj(A+"/quick-cmd-settings"),
        ctpls=await fj(A+"/cmd-templates"),
        savedPd=await fj(A+"/quick-cmds/config");
    window._qcs=qcs||{};
    window._ctpls=ctpls||[];
    var pdDefault={world:[["设为白天","time set 1000"],["设为黑夜","time set 13000"],["晴天","weather clear"],["雨天","weather rain"],["雷暴","weather thunder"],["开启爆炸破坏","gamerule mobGriefing true"],["关闭爆炸破坏","gamerule mobGriefing false"],["允许TNT","gamerule tntExplosionDropDecay false"],["禁止TNT","gamerule tntExplosionDropDecay true"],["开启死亡不掉落","gamerule keepInventory true"],["关闭死亡不掉落","gamerule keepInventory false"],["睡觉比例1人","gamerule playersSleepingPercentage 0"],["睡觉比例50%","gamerule playersSleepingPercentage 50"],["睡觉比例100%","gamerule playersSleepingPercentage 100"],["禁用昼夜循环","gamerule doDaylightCycle false"],["启用昼夜循环","gamerule doDaylightCycle true"]],player:[["给予物品 give","give <player> minecraft:"],["设为创造","gamemode creative <player>"],["设为生存","gamemode survival <player>"],["设为观察者","gamemode spectator <player>"],["设为冒险","gamemode adventure <player>"],["设置昵称 nick","nick <player> "],["增加经验","xp add <player> 100"],["加血 heal","heal <player>"],["喂食 feed","feed <player>"],["传送至玩家 tpa","tpa <player>"],["踢出 kick","kick <player>"],["清空背包 clear","clear <player>"],["授予飞行","fly <player> enable"],["邀请组队","ftbteams invite <player>"],["查看背包 invsee","invsee <player>"]],ftb_ess:[["返回死亡点 /back","back"],["返回出生点 /spawn","spawn"],["传送请求 /tpa","tpa"],["接受传送","tpa accept"],["回家 /home","home"],["设置家 /sethome","sethome"],["传送点 /warp","warp"],["治疗 /heal","heal"],["喂饱 /feed","feed"],["切换飞行 /fly","fly"],["设置传送点 /setwarp","setwarp"],["在线列表 /list","list"],["随机传送 /rtp","rtp"]],ftb_teams:[["创建队伍","ftbteams create"],["邀请玩家","ftbteams invite"],["接受邀请","ftbteams join"],["离开队伍","ftbteams leave"],["队伍信息","ftbteams info"],["队伍设置","ftbteams settings"],["转让队长","ftbteams transfer"],["踢出成员","ftbteams kick"],["队伍聊天","ftbteams msg"]],ftb_more:[["FTB 区块管理","ftbchunks"],["声明区块","ftbchunks claim"],["取消声明","ftbchunks unclaim"],["FTB 任务书","ftbquests"],["连锁采集切换","ftbultimine"],["积分交易","ftbshop"]]};
    var pd={};
    for(var k in pdDefault){
        pd[k]=savedPd&&savedPd[k]?savedPd[k]:pdDefault[k];
    }
    window._pdDefault=pdDefault;
    window._pdCurrent=pd;
    var h='<div class="fb" style="margin-bottom:12px"><h3 style="margin:0">快捷命令转发</h3><button class="b2 bsm" onclick="showQcConfig()" style="margin-left:12px">⚙️ 配置</button></div>';
    h+='<div class="ct" style="margin-bottom:12px"><div class="fr"><div class="fg"><label>目标群聊</label><select id="cmd-gid" onchange="updCmdSrv()">';
    for(var id in g){var nm=gn(g[id]);h+='<option value="'+id+'">'+(nm||'群 '+id)+'</option>'}
    h+='</select></div><div class="fg"><label>目标服务器</label><select id="cmd-sidx"></select></div></div>';
    h+='<div class="fg"><label>执行结果</label><pre id="cmd-out" style="min-height:40px;font-size:11px;color:var(--m)">选择命令后执行</pre></div></div>';
    h+='<div class="fb" style="margin-bottom:10px"><div class="fbar">';
    var ctabs=[{k:"world",n:"🌍 世界设置"},{k:"player",n:"👤 玩家命令"},{k:"ftb_ess",n:"📦 FTB Essentials"},{k:"ftb_teams",n:"👥 FTB 团队"},{k:"ftb_more",n:"🔧 更多"}];
    for(var i=0;i<ctabs.length;i++)h+='<button class="b2 bsm cmd-tb" data-ct="'+ctabs[i].k+'" onclick="swCmdTab(\''+ctabs[i].k+'\')">'+ctabs[i].n+'</button>';
    h+='</div></div>';
    for(var j=0;j<ctabs.length;j++){
        var k=ctabs[j].k,cs=pd[k]||[],disp=j===0?"block":"none";
        h+='<div class="ct cmd-grp" id="cg-'+k+'" style="display:'+disp+'"><h3>'+ctabs[j].n+'</h3>';
        if(k==="player"){
            h+='<div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;background:var(--bg);border:1px solid var(--b);border-radius:6px;padding:8px 12px">';
            h+='<span style="color:var(--s);font-weight:600;white-space:nowrap;font-size:13px">👤 目标玩家</span>';
            h+='<input id="qc-player-name" placeholder="输入玩家名，下方命令中的 &lt;player&gt; 自动替换" style="flex:1">';
            h+='</div>';
        }
        h+='<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:6px">';
        for(var ci=0;ci<cs.length;ci++){
            var l=cs[ci][0],c=cs[ci][1];
            var ckey=c;
            var qs=window._qcs[ckey]||{};
            var en=qs.enabled===true;
            h+='<div class="qc-box">';
            h+='<label class="tg qc-tg" title="启用/禁用此命令"><input type="checkbox" '+(en?'checked':'')+' onchange="tglQc(\''+ckey.replace(/'/g,"\\'")+'\',this.checked,this)"><span class="sl"></span></label>';
            h+='<button class="b2 bsm'+(en?'':' qc-off')+'" data-qc="'+ckey+'" onclick="doQc(this)" title="/'+c+'">'+l+'</button>';
            h+='</div>';
        }
        h+='</div></div>';
    }
    h+='<div class="ct" style="margin-top:12px"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px"><h3 style="margin:0">📋 命令模板</h3><button class="b1 bsm" onclick="adCmdTpl()">+ 新建模板</button></div>';
    if(ctpls&&ctpls.length){
        ctpls.forEach(function(v,i){
            var en=v.enabled!==false;
            h+='<div style="background:var(--bg);border:1px solid var(--b);border-radius:6px;padding:12px;margin-bottom:8px">';
            h+='<div style="display:flex;justify-content:space-between;align-items:flex-start"><div style="flex:1">';
            h+='<strong>'+v.name+'</strong>';
            h+='<label class="tg" style="margin-left:8px;vertical-align:middle"><input type="checkbox" '+(en?'checked':'')+' onchange="tglCd('+i+',this.checked)"><span class="sl"></span></label>';
            h+='<span style="color:var(--m);font-size:10px;margin-left:6px">'+(en?'启用':'禁用')+'</span>';
            h+='<span style="color:var(--m);font-size:10px;margin-left:8px">'+(v.desc||'')+'</span>';
            h+='<pre style="margin:6px 0 0;font-size:11px;color:var(--s)">'+(v.commands||[]).join("\n")+'</pre></div>';
            h+='<div class="ac"><button class="b1 bsm" onclick="execCmdTpl('+i+')">▶ 执行</button><button class="b2 bsm" onclick="edCmdTpl('+i+')">编辑</button><button class="bd bsm" onclick="rmCmdTpl(\''+(v.name||'').replace(/'/g,"\\'")+'\')">删除</button></div></div></div>';
        });
    }else{
        h+='<div class="emp">暂无命令模板，点击上方按钮创建</div>';
    }
    h+='</div>';
    h+='<div class="ct" style="margin-top:12px"><h3>自定义命令</h3><div class="if"><input id="cmd-custom" placeholder="输入 RCON 命令 (如: say Hello)" onkeyup="if(event.key===\'Enter\')doRconCmd(this.value)"><button class="b1 bs" onclick="doRconCmd(document.getElementById(\'cmd-custom\').value)">发送</button></div></div>';
    document.getElementById("main").innerHTML=h;
    updCmdSrv();
    swCmdTab(cmdTab);
}
function updCmdSrv(){var g=document.getElementById("cmd-gid").value;fetch(A+"/groups?filter_web_mgmt=1").then(function(r){return r.json()}).then(function(d){var s=d[g]||[],sel=document.getElementById("cmd-sidx");sel.innerHTML="";for(var i=0;i<s.length;i++){var n=s[i].server_name||s[i].name||"服务器"+i;sel.innerHTML+='<option value="'+i+'">'+n+'</option>'}})}
var cmdTab="world";
function swCmdTab(t){cmdTab=t;document.querySelectorAll(".cmd-tb").forEach(function(b){b.className="b2 bsm cmd-tb";if(b.dataset.ct===t)b.className="b1 bsm cmd-tb"});document.querySelectorAll(".cmd-grp").forEach(function(d){d.style.display="none"});var cg=d.getElementById("cg-"+t);if(cg)cg.style.display="block"}
function showQcConfig(){
    var pd=window._pdCurrent||{};
    var catNames={world:"🌍 世界设置",player:"👤 玩家命令",ftb_ess:"📦 FTB Essentials",ftb_teams:"👥 FTB 团队",ftb_more:"🔧 更多"};
    var m='<div class="mbg" id="qc-cfg-m" onclick="if(event.target===this)this.remove()"><div class="mod" style="max-width:750px"><h3>⚙️ 快捷命令配置</h3>';
    m+='<p style="font-size:11px;color:var(--m);margin-bottom:4px">每行一条命令，格式: <code>["标签", "命令"]</code>。参数用 <code>&lt;参数名&gt;</code> 标记，如 <code>&lt;player&gt;</code></p>';
    m+='<p style="font-size:11px;color:var(--s);margin-bottom:10px">修改后点保存，下次打开页面即生效。可复制粘贴到别处备份。</p>';
    for(var k in catNames){
        var cs=pd[k]||[];
        var json=JSON.stringify(cs,null,2);
        m+='<div class="fg" style="margin-bottom:8px"><label style="font-weight:600">'+catNames[k]+'</label>';
        m+='<textarea id="qc-cfg-'+k+'" rows="'+Math.max(5,cs.length+2)+'" style="font-family:monospace;font-size:11px;white-space:pre;overflow-x:auto">'+json+'</textarea></div>';
    }
    m+='<div style="margin-top:12px;display:flex;gap:8px"><button class="b1 bs" onclick="saveQcConfig()">💾 保存</button><button class="b2 bs" onclick="document.getElementById(\'qc-cfg-m\').remove()">取消</button></div></div></div>';
    document.body.insertAdjacentHTML("beforeend",m);
}
async function saveQcConfig(){
    var catNames={world:"🌍 世界设置",player:"👤 玩家命令",ftb_ess:"📦 FTB Essentials",ftb_teams:"👥 FTB 团队",ftb_more:"🔧 更多"};
    var data={},errs=[];
    for(var k in catNames){
        try{data[k]=JSON.parse(document.getElementById("qc-cfg-"+k).value)}catch(e){errs.push(catNames[k]+": "+e.message)}
    }
    if(errs.length){toast("JSON 格式错误:\n"+errs.join("\n"),true);return}
    await pjt(A+"/quick-cmds/config",data);
    document.getElementById("qc-cfg-m")?.remove();
    window._pdCurrent=data;
    // 重新渲染命令网格
    for(var k in data){
        var g=d.getElementById("cg-"+k),cs=data[k]||[];
        if(!g)continue;
        var h='';
        for(var ci=0;ci<cs.length;ci++){
            var l=cs[ci][0],c=cs[ci][1],ckey=c;
            var qs=window._qcs[ckey]||{},en=qs.enabled===true;
            h+='<div class="qc-box">';
            h+='<label class="tg qc-tg" title="启用/禁用此命令"><input type="checkbox" '+(en?'checked':'')+' onchange="tglQc(\''+ckey.replace(/'/g,"\\\\'")+'\',this.checked,this)"><span class="sl"></span></label>';
            h+='<button class="b2 bsm'+(en?'':' qc-off')+'" data-qc="'+ckey+'" onclick="doQc(this)" title="/'+c+'">'+l+'</button>';
            h+='</div>';
        }
        g.querySelector('div[style*="grid"]').innerHTML=h;
    }
    toast("已保存");
}
function doQc(el){
    var en=el.parentElement.querySelector('.qc-tg input[type="checkbox"]');
    if(!en||!en.checked){toast("命令已禁用",true);return}
    var cmd=el.getAttribute("data-qc");
    var pn=document.getElementById("qc-player-name");
    if(pn&&pn.value.trim()&&cmd.indexOf("<player>")>=0){
        cmd=cmd.replace(/<player>/g,pn.value.trim());
    }
    doRconCmd(cmd);
}
async function tglQc(cmd,enabled,cb){
    try{
        var q=window._qcs||{};
        q[cmd]=q[cmd]||{};
        q[cmd].enabled=enabled;
        window._qcs=q;
        await pjt(A+"/quick-cmd-settings/"+encodeURIComponent(cmd),{enabled:enabled});
        var btns=document.querySelectorAll('[data-qc="'+cmd.replace(/"/g,"&quot;")+'"]');
        btns.forEach(function(b){
            if(enabled)b.classList.remove('qc-off');
            else b.classList.add('qc-off');
            var inp=b.parentElement.querySelector('.qc-tg input');
            if(inp)inp.checked=enabled;
        });
    }catch(e){
        if(cb)cb.checked=!enabled;
        toast(e.message,true);
    }
}
async function doRconCmd(cmd){if(!cmd||!cmd.trim())return;var params=extractParams(cmd);var gid=document.getElementById("cmd-gid").value,sidx=parseInt(document.getElementById("cmd-sidx").value)||0;showExecDlg("执行命令",[cmd],params,gid,sidx)}
/* ====== 通用执行弹窗（参数检测 + 确认发送） ====== */
function extractParams(cmd){var re=/[<{]([^>}]+)[>}]/g,m,p=[];while((m=re.exec(cmd))!==null){var k=m[1].toLowerCase().replace(/[^a-z0-9_]/g,"_");if(!p.some(function(x){return x.key===k})){p.push({key:k,label:m[1],default:""})}}return p}
function showExecDlg(title,cmds,params,gid,sidx){window._exDlgCmds=cmds||[];window._exDlgParams=params||[];window._exDlgGid=gid;window._exDlgSidx=sidx;var m='<div class="mbg" id="exd-m" onclick="if(event.target===this)this.remove()"><div class="mod" style="max-width:500px"><h3>'+title+'</h3>';if(cmds&&cmds.length){m+='<div style="font-size:11px;color:var(--m);margin-bottom:10px;word-break:break-all">';cmds.forEach(function(c){m+='<code>'+c+'</code><br>'});m+='</div>'}if(params.length){params.forEach(function(p){m+='<div class="fg"><label>'+p.label+'</label><input id="xp-'+p.key+'" value="'+(p.default||'')+'" placeholder="'+p.label+'"></div>'})}m+='<div style="margin-top:14px;display:flex;gap:8px"><button class="b1 bs" onclick="execWithParams()">▶ 发送</button><button class="b2 bs" onclick="document.getElementById(\'exd-m\').remove()">取消</button></div></div></div>';document.body.insertAdjacentHTML("beforeend",m)}
async function execWithParams(){var cmds=window._exDlgCmds||[],params=window._exDlgParams||[],gid=window._exDlgGid||'',sidx=window._exDlgSidx||0;var values={};params.forEach(function(p){values[p.key]=document.getElementById("xp-"+p.key).value});var out=document.getElementById("cmd-out")||window._etOut;if(out){out.textContent="执行中...";out.style.color="var(--m)"}var results=[];for(var i=0;i<cmds.length;i++){var cmd=cmds[i];for(var k in values){cmd=cmd.split("{"+k+"}").join(values[k]).split("<"+params.find(function(x){return x.key===k})?.label+">").join(values[k])}try{var r=await pj(A+"/rcon/exec",{group_id:gid,server_index:sidx,command:cmd});results.push(r.response||"(无输出)")}catch(e){results.push("✗ "+cmd+": "+e.message)}}document.getElementById("exd-m")?.remove();if(out){out.textContent=results.join("\n");out.style.color="var(--t)"}window._etOut=null}
/* 玩家快捷命令 */
function edPlayerCmd(qq,mcid){if(!mcid||mcid==="未绑定"){toast("该玩家未绑定 MC ID",true);return}var cmds=[["给予物品 give","give "+mcid+" minecraft:"],["设为创造","gamemode creative "+mcid],["设为生存","gamemode survival "+mcid],["设为观察者","gamemode spectator "+mcid],["设为冒险","gamemode adventure "+mcid],["设置昵称 nick","nick "+mcid+" "],["增加经验","xp add "+mcid+" 100"],["治疗","heal "+mcid],["喂饱","feed "+mcid],["传送至玩家","tpa "+mcid],["踢出","kick "+mcid],["清空背包","clear "+mcid],["授予飞行","fly "+mcid+" enable"],["邀请组队","ftbteams invite "+mcid],["查看背包","invsee "+mcid]];var h='<div class="mbg" id="et-m" onclick="if(event.target===this)this.remove()"><div class="mod"><h3>快捷命令 - '+mcid+'</h3><p style="font-size:11px;color:var(--m);margin-bottom:6px">目标: '+mcid+' | QQ: '+qq+'</p><div class="fg"><label>目标群聊</label><select id="et-gid"></select></div><div class="fg"><label>目标服务器</label><select id="et-sidx"></select></div><div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:12px">';for(var i=0;i<cmds.length;i++){var l=cmds[i][0],c=cmds[i][1];h+='<button class="b2 bsm" onclick="execRCmd(\''+c.replace(/'/g,"\\'")+'\')">'+l+'</button>'}h+='</div><div class="fg"><label>自定义命令</label><div class="if"><input id="et-custom" placeholder="输入 RCON 命令"><button class="b1 bsm" onclick="execRCmd(document.getElementById(\'et-custom\').value)">发送</button></div></div><pre id="et-out" style="min-height:30px;font-size:11px;color:var(--m);margin-top:6px">选择命令后执行</pre><button class="b2 bs" style="margin-top:10px" onclick="document.getElementById(\'et-m\').remove()">关闭</button></div></div>';document.body.insertAdjacentHTML("beforeend",h);fetch(A+"/groups?filter_web_mgmt=1").then(function(r){return r.json()}).then(function(d){var gs=d.getElementById("et-gid"),ss=d.getElementById("et-sidx");for(var id in d){var nm=gn(d[id]);gs.innerHTML+='<option value="'+id+'">'+(nm||'群 '+id)+'</option>'};gs.onchange=function(){var gid=gs.value,s=d[gid]||[];ss.innerHTML="";for(var i=0;i<s.length;i++){var n=s[i].server_name||s[i].name||"服务器"+i;ss.innerHTML+='<option value="'+i+'">'+n+'</option>'}};gs.onchange()})}
async function execRCmd(cmd){if(!cmd||!cmd.trim())return;var params=extractParams(cmd);var gid=document.getElementById("et-gid").value,sidx=parseInt(document.getElementById("et-sidx").value)||0;showExecDlg("执行命令",[cmd],params,gid,sidx);window._etOut=document.getElementById("et-out")}
/* ====== 全局设置 (可编辑表单) ====== */
async function loCfg(){var c=await fj(A+"/config/all"),h='<div class="ct sf"><h3>⚙️ 全局设置</h3><form id="cfg-form" onsubmit="doSaveCfg();return false"><div class="sg">';h+='<div class="sg-item"><h4>⚡ 速率限制</h4><div class="fr"><div class="fg"><label>速率限制开关</label><select id="cfg-rate-enabled"><option value="1" '+(c.rate_enabled?'selected':'')+'>开启</option><option value="0" '+(!c.rate_enabled?'selected':'')+'>关闭</option></select></div><div class="fg"><label>基础间隔(毫秒)</label><input type="number" id="cfg-rate-base-ms" value="'+(c.rate_base_ms||1000)+'"></div></div><div class="fr"><div class="fg"><label>窗口时间(分钟)</label><input type="number" id="cfg-rate-window-minutes" value="'+Math.floor((c.rate_window_s||300)/60)+'"></div><div class="fg"><label>触发阈值(次数)</label><input type="number" id="cfg-rate-threshold" value="'+(c.rate_threshold||10)+'"></div></div><div class="fr"><div class="fg"><label>增量(毫秒)</label><input type="number" id="cfg-rate-increment-ms" value="'+(c.rate_increment_ms||500)+'"></div><div class="fg"><label>最大间隔(毫秒)</label><input type="number" id="cfg-rate-max-ms" value="'+(c.rate_max_ms||10000)+'"></div></div><div class="fr"><div class="fg"><label>自动恢复</label><select id="cfg-rate-auto-recovery"><option value="1" '+(c.rate_auto_recovery?'selected':'')+'>开启</option><option value="0" '+(!c.rate_auto_recovery?'selected':'')+'>关闭</option></select></div><div class="fg"><label>恢复时间(分钟)</label><input type="number" id="cfg-rate-recovery-minutes" value="'+Math.floor((c.rate_recovery_s||600)/60)+'"></div></div></div>';h+='<div class="sg-item"><h4>👤 频率白名单</h4><p style="font-size:10px;color:var(--m);margin-bottom:8px">白名单用户与管理员不受频繁限制，但仍受最低硬延迟约束</p><div class="fr"><div class="fg"><label>白名单用户(每行一个QQ)</label><textarea id="cfg-rate-wl" rows="3">'+((c.rate_whitelist||[]).join("\n"))+'</textarea></div><div class="fg"><label>最低硬延迟(毫秒)</label><input type="number" id="cfg-rate-wl-min-delay" value="'+(c.rate_whitelist_min_delay_ms||200)+'" min="200" title="硬编码最小200ms，防止频繁转发导致服务器性能压力"></div></div></div>';h+='<div class="sg-item"><h4>🔍 在线追踪</h4><div class="fr"><div class="fg"><label>追踪开关</label><select id="cfg-tk-on"><option value="1" '+(c.tracker_enabled?'selected':'')+'>开启</option><option value="0" '+(!c.tracker_enabled?'selected':'')+'>关闭</option></select></div><div class="fg"><label>查询方式</label><select id="cfg-tk-method"><option value="rcon" '+((c.tracker_method||'rcon')==='rcon'?'selected':'')+'>RCON</option><option value="mcstatus" '+((c.tracker_method||'')==='mcstatus'?'selected':'')+'>MCStatus</option></select></div></div><div class="fr"><div class="fg"><label>提醒开关</label><select id="cfg-tk-notify"><option value="1" '+(c.tracker_notify?'selected':'')+'>开启</option><option value="0" '+(!c.tracker_notify?'selected':'')+'>关闭</option></select></div><div class="fg"><label>提醒目标</label><select id="cfg-tk-target"><option value="group" '+((c.tracker_notify_target||'group')==='group'?'selected':'')+'>群聊</option><option value="admin_dm" '+((c.tracker_notify_target||'')==='admin_dm'?'selected':'')+'>管理员私聊</option></select></div><div class="fg"><label>提醒节点(分钟,逗号分隔)</label><input id="cfg-tk-intervals" value="'+(c.tracker_notify_intervals||[]).join(',')+'"></div></div><div class="fr"><div class="fg"><label>游戏内提醒</label><select id="cfg-tk-notify-game"><option value="1" '+(c.tracker_notify_game?'selected':'')+'>开启</option><option value="0" '+(!c.tracker_notify_game?'selected':'')+'>关闭</option></select></div><div class="fg"><label>游戏提醒格式</label><input id="cfg-tk-fmt-game" value="'+(c.tracker_notify_game_fmt||'')+'"></div><div class="fg"><label>提醒前缀</label><input id="cfg-tk-prefix-game" value="'+(c.tracker_notify_game_prefix||'§e[在线提醒]')+'"></div><div class="fg"><label>自动踢出</label><select id="cfg-tk-kick"><option value="1" '+(c.tracker_kick_enabled?'selected':'')+'>开启</option><option value="0" '+(!c.tracker_kick_enabled?'selected':'')+'>关闭</option></select></div></div><div class="fr"><div class="fg"><label>踢出阈值(分钟)</label><input type="number" id="cfg-tk-threshold" value="'+(c.tracker_kick_threshold||720)+'"></div><div class="fg"><label>封禁时长(分钟)</label><input type="number" id="cfg-tk-ban" value="'+(c.tracker_ban_minutes||30)+'"></div></div><div class="fr"><div class="fg"><label>单次记录时长(小时,0=永久保留)</label><input type="number" id="cfg-tk-rank-reset" value="'+(c.ranking_reset_hours||0)+'"></div><div class="fg"><label>柱状图条数</label><input type="number" id="cfg-tk-max-bars" value="'+(c.online_history_max_bars||70)+'" title="在线时长柱状图最多显示条数"></div></div></div>';h+='<div class="sg-item"><h4>📁 通用</h4><div class="fr"><div class="fg"><label>脚本目录</label><input id="cfg-scripts-dir" value="'+(c.scripts_dir||'scripts')+'"></div><div class="fg"><label>RCON保活间隔(秒)</label><input type="number" id="cfg-keepalive-int" value="'+(c.rcon_keepalive_interval||180)+'" min="0" title="0=禁用保活。应小于MC服务端RCON空闲超时，推荐180"></div></div><div class="fr" style="margin-top:8px"><div class="fg"><label>RCON空闲断开(秒)</label><input type="number" id="cfg-idle-disc" value="'+(c.rcon_idle_disconnect||0)+'" min="0" title="0=不自动断开。连接空闲超时后主动关闭以节省资源"></div></div><div class="fr" style="margin-top:8px"><div class="fg"><label>RCON连接模式</label><select id="cfg-rcn-persistent" title="常连接模式下RCON连接保持不断，减少MC服务端日志刷屏。推荐开启"><option value="1" '+(c.rcn_persistent!==false?'selected':'')+'>常连接（推荐）</option><option value="0" '+(c.rcn_persistent===false?'selected':'')+'>短连接</option></select></div><div class="fg"><label>扫描模式</label><select id="cfg-tk-poll-mode" onchange="var v=this.value;document.getElementById(\'cfg-tk-interval\').parentElement.style.display=v===\'smart\'?\'none\':\'\';document.getElementById(\'cfg-tk-idle\').style.display=v===\'smart\'?\'\':\'none\';document.getElementById(\'cfg-tk-active\').style.display=v===\'smart\'?\'\':\'none\'"><option value="frequent" '+((c.tracker_poll_mode||'frequent')==='frequent'?'selected':'')+'>频繁模式</option><option value="smart" '+((c.tracker_poll_mode||'')==='smart'?'selected':'')+'>有人模式</option><option value="custom" '+((c.tracker_poll_mode||'')==='custom'?'selected':'')+'>自定模式</option></select></div><div class="fg"><label>轮询间隔(秒)</label><input type="number" id="cfg-tk-interval" value="'+(c.tracker_interval||60)+'"></div></div><div class="fr" style="margin-top:8px"><div class="fg" id="cfg-tk-idle" style="display:'+((c.tracker_poll_mode||'frequent')==='smart'?'':'none')+'"><label>无人间隔(秒)</label><input type="number" id="cfg-tk-idle-int" value="'+(c.tracker_idle_interval||300)+'"></div><div class="fg" id="cfg-tk-active" style="display:'+((c.tracker_poll_mode||'frequent')==='smart'?'':'none')+'"><label>有人间隔(秒)</label><input type="number" id="cfg-tk-active-int" value="'+(c.tracker_active_interval||60)+'"></div><div class="fg"><label>事件宏说前缀</label><input id="cfg-em-game-prefix" value="'+(c.event_macro_game_prefix||'§b[宏]')+'" title="事件宏执行 say 命令时自动添加此前缀"></div><div class="fg"><label>通用通知前缀</label><input id="cfg-gn-game-prefix" value="'+(c.game_notify_prefix||'§6[通知]')+'" title="插件主动发送的游戏内通知前缀"></div></div></div>';h+='<div class="sg-item"><h4>👤 玩家数据库</h4><div class="fr"><div class="fg"><label>玩家DB开关</label><select id="cfg-pdb-enabled"><option value="1" '+(c.pdb_enabled?'selected':'')+'>开启</option><option value="0" '+(!c.pdb_enabled?'selected':'')+'>关闭</option></select></div><div class="fg"><label>签到积分</label><input type="number" id="cfg-pdb-checkin-pts" value="'+(c.pdb_checkin_pts||10)+'"></div></div><div class="fr"><div class="fg"><label>连签加成</label><input type="number" id="cfg-pdb-streak-bonus" value="'+(c.pdb_streak_bonus||2)+'"></div><div class="fg"><label>新玩家积分</label><input type="number" id="cfg-pdb-new-pts" value="'+(c.pdb_new_pts||50)+'"></div></div><div class="fr"><div class="fg"><label>补偿功能</label><select id="cfg-pdb-comp-enabled"><option value="1" '+(c.pdb_comp_enabled?'selected':'')+'>开启</option><option value="0" '+(!c.pdb_comp_enabled?'selected':'')+'>关闭</option></select></div><div class="fg"><label>补偿冷却(小时)</label><input type="number" id="cfg-pdb-comp-cooldown" value="'+(c.pdb_comp_cooldown_hours||24)+'"></div></div><div class="fr"><div class="fg"><label>补偿白名单(每行一个QQ)</label><textarea id="cfg-pdb-comp-wl" rows="3">'+((c.pdb_comp_whitelist||[]).join("\n"))+'</textarea></div><div class="fg"><label>需管理员审批</label><select id="cfg-pdb-comp-admin"><option value="1" '+(c.pdb_comp_require_admin!==false?'selected':'')+'>是</option><option value="0" '+(c.pdb_comp_require_admin===false?'selected':'')+'>否</option></select></div></div><div class="fr"><div class="fg"><label>补偿命令黑名单(每行一个关键词)</label><textarea id="cfg-pdb-comp-bl" rows="3">'+((c.pdb_comp_blacklist||[]).join("\n"))+'</textarea></div></div></div>';h+='<div class="sg-item"><h4>🗄️ 数据库存储</h4><p style="font-size:11px;color:var(--m);margin-bottom:8px">玩家数据与在线记录共用同一数据库</p><div class="fr"><div class="fg"><label>存储模式</label><select id="cfg-pdb-storage-mode"><option value="local" '+((c.pdb_storage_mode||"local")=="local"?"selected":"")+'>仅本地</option><option value="external" '+((c.pdb_storage_mode||"")=="external"?"selected":"")+'>仅云端</option><option value="dual" '+((c.pdb_storage_mode||"")=="dual"?"selected":"")+'>双端</option></select></div><div class="fg"><label>读取来源</label><select id="cfg-pdb-read-source"><option value="local" '+((c.pdb_read_source||"local")=="local"?"selected":"")+'>本地</option><option value="external" '+((c.pdb_read_source||"")=="external"?"selected":"")+'>云端</option></select></div></div><div class="fr"><div class="fg"><label style="width:110px">云端DB路径 (SQLite)</label><input id="cfg-pdb-ext-db-path" value="'+(c.pdb_ext_db_path||"")+'" placeholder="如 D:/shared/mc_data.db"></div><div class="fg"><label style="width:110px">云端主机</label><input id="cfg-pdb-ext-host" value="'+(c.pdb_ext_host||"")+'" placeholder="127.0.0.1"></div></div><div class="fr"><div class="fg"><label style="width:110px">端口</label><input type="number" id="cfg-pdb-ext-port" value="'+(c.pdb_ext_port||3306)+'"></div><div class="fg"><label style="width:110px">用户名</label><input id="cfg-pdb-ext-user" value="'+(c.pdb_ext_user||"")+'" placeholder="root"></div></div><div class="fr"><div class="fg"><label style="width:110px">密码</label><input type="password" id="cfg-pdb-ext-password" value="'+(c.pdb_ext_password||"")+'" placeholder="留空不修改"></div><div class="fg"><label style="width:110px">数据库名</label><input id="cfg-pdb-ext-database" value="'+(c.pdb_ext_database||"")+'" placeholder="mc_players"></div></div><p style="font-size:10px;color:var(--m);margin-top:4px">云端数据库需插件重启后生效。双端模式同时存储到本地和云端</p></div>';h+='<div class="sg-item"><h4>💬 群服互联</h4><div class="fr"><div class="fg"><label>互联开关</label><select id="cfg-relay-on"><option value="1" '+(c.relay_enabled?'selected':'')+'>开启</option><option value="0" '+(!c.relay_enabled?'selected':'')+'>关闭</option></select></div><div class="fg"><label>群→MC</label><select id="cfg-relay-g2m"><option value="1" '+(c.relay_group_to_mc?'selected':'')+'>开启</option><option value="0" '+(!c.relay_group_to_mc?'selected':'')+'>关闭</option></select></div><div class="fg"><label>MC→群</label><select id="cfg-relay-m2g"><option value="1" '+(c.relay_mc_to_group?'selected':'')+'>开启</option><option value="0" '+(!c.relay_mc_to_group?'selected':'')+'>关闭</option></select></div></div><div class="fr"><div class="fg"><label>群→MC格式</label><input id="cfg-relay-fg" value="'+(c.relay_fmt_group||'')+'"></div><div class="fg"><label>MC→群格式</label><input id="cfg-relay-fm" value="'+(c.relay_fmt_mc||'')+'"></div></div></div>';h+='<div class="sg-item"><h4>🔐 管理员与安全</h4><div class="fg"><label>管理员QQ列表（每行一个QQ号）</label><textarea id="cfg-admin-qqs">'+((c.admin_qqs||[]).join("\n"))+'</textarea></div><div class="fr"><div class="fg"><label>RCON超时(秒)</label><input type="number" id="cfg-rcon-timeout" value="'+(c.rcon_timeout||5)+'"></div><div class="fg"><label>选服TTL(秒)</label><input type="number" id="cfg-select-ttl" value="'+(c.select_ttl||30)+'"></div></div></div>';h+='<div class="sg-item"><h4>📡 日志监听</h4><div class="fr"><div class="fg"><label>监听开关</label><select id="cfg-tk-log-listen" title="监控服务器 latest.log 日志文件。关闭后日志查看器、日志事件宏、日志驱动服→群转发均停止工作"><option value="1" '+(c.log_listener_enabled?'selected':'')+'>✅ 开启</option><option value="0" '+(!c.log_listener_enabled?'selected':'')+'>❌ 关闭</option></select></div><div class="fg"><label>日志刷新(ms)</label><input type="number" id="cfg-lv-refresh" value="'+(c.log_viewer_refresh_ms||10000)+'" min="0" title="日志查看器自动刷新间隔。设0关闭自动刷新。⚠ 间隔越短日志刷屏越严重"></div></div><div class="fg"><label>说明</label><span style="font-size:10px;color:var(--m);line-height:1.5">① 需在<a href="javascript:nav(\'servers\')" style="color:var(--a)">服务器管理</a>中为对应服务器填写日志路径，保存后插件重启即自动监听<br>② MC 服务端日志文件需可被插件进程读取<br>③ Docker场景下MC在另一容器时需先配置卷挂载，否则插件无法读取日志<br>④ 保存后即时生效，无需重启<br>⚠ 刷新间隔 &lt;3000ms 会导致控制台大量刷屏</span></div></div></div>';h+='<div class="sg-item"><h4>📡 查询显示</h4><div class="fr"><div class="fg"><label>地址端口</label><select id="cfg-sq-addr"><option value="1" '+(c.show_addr_port!==false?'selected':'')+'>显示</option><option value="0" '+(c.show_addr_port===false?'selected':'')+'>隐藏</option></select></div><div class="fg"><label>版本</label><select id="cfg-sq-ver"><option value="1" '+(c.show_ver!==false?'selected':'')+'>显示</option><option value="0" '+(c.show_ver===false?'selected':'')+'>隐藏</option></select></div><div class="fg"><label>延迟</label><select id="cfg-sq-lat"><option value="1" '+(c.show_lat!==false?'selected':'')+'>显示</option><option value="0" '+(c.show_lat===false?'selected':'')+'>隐藏</option></select></div></div><div class="fr"><div class="fg"><label>在线人数</label><select id="cfg-sq-on"><option value="1" '+(c.show_on!==false?'selected':'')+'>显示</option><option value="0" '+(c.show_on===false?'selected':'')+'>隐藏</option></select></div><div class="fg"><label>玩家列表</label><select id="cfg-sq-pl"><option value="1" '+(c.show_pl!==false?'selected':'')+'>显示</option><option value="0" '+(c.show_pl===false?'selected':'')+'>隐藏</option></select></div><div class="fg"><label>渲染为图片</label><select id="cfg-sq-img"><option value="1" '+(c.render_img?'selected':'')+'>开启</option><option value="0" '+(!c.render_img?'selected':'')+'>关闭</option></select></div></div><div class="fr"><div class="fg"><label>自动清理(天)</label><input type="number" id="cfg-sq-clean" value="'+(c.auto_cleanup_days||10)+'"></div></div></div>';h+='<div class="sg-item sg-full"><h4>🚫 危险命令黑名单（每行一个关键词）</h4><div class="fg"><textarea id="cfg-dangerous" rows="5">'+((c.dangerous_blacklist||[]).join("\n"))+'</textarea></div></div>';h+='</div><div style="margin-top:20px;padding-top:16px;border-top:1px solid var(--b)"><button class="b1 bs" type="submit">💾 保存所有设置</button><button class="b2 bs" type="button" onclick="loCfg().catch(function(e){toast(\'重新加载失败: \'+e.message,true)})" style="margin-left:8px">🔄 重新加载</button></div></form></div>';document.getElementById("main").innerHTML=h}
async function doSaveCfg(){
    var b={
        admin_qqs:document.getElementById("cfg-admin-qqs").value.split("\n").map(function(s){return s.trim()}).filter(Boolean),
        rcon_timeout:parseInt(document.getElementById("cfg-rcon-timeout").value)||5,
        select_ttl:parseInt(document.getElementById("cfg-select-ttl").value)||30,
        rate_enabled:document.getElementById("cfg-rate-enabled").value=="1",
        rate_base_ms:parseInt(document.getElementById("cfg-rate-base-ms").value)||1000,
        rate_window_minutes:parseInt(document.getElementById("cfg-rate-window-minutes").value)||5,
        rate_threshold:parseInt(document.getElementById("cfg-rate-threshold").value)||10,
        rate_increment_ms:parseInt(document.getElementById("cfg-rate-increment-ms").value)||500,
        rate_max_ms:parseInt(document.getElementById("cfg-rate-max-ms").value)||10000,
        rate_auto_recovery:document.getElementById("cfg-rate-auto-recovery").value=="1",
        rate_recovery_minutes:parseInt(document.getElementById("cfg-rate-recovery-minutes").value)||10,
        rate_whitelist_qqs:document.getElementById("cfg-rate-wl").value.split("\n").map(function(s){return s.trim()}).filter(Boolean),
        rate_whitelist_min_delay_ms:Math.max(200,parseInt(document.getElementById("cfg-rate-wl-min-delay").value)||200),
        pdb_enabled:document.getElementById("cfg-pdb-enabled").value=="1",
        pdb_checkin_pts:parseInt(document.getElementById("cfg-pdb-checkin-pts").value)||10,
        pdb_streak_bonus:parseInt(document.getElementById("cfg-pdb-streak-bonus").value)||2,
        pdb_new_pts:parseInt(document.getElementById("cfg-pdb-new-pts").value)||50,
        pdb_comp_enabled:document.getElementById("cfg-pdb-comp-enabled").value=="1",
        pdb_comp_cooldown_hours:parseInt(document.getElementById("cfg-pdb-comp-cooldown").value)||24,
        pdb_comp_whitelist:document.getElementById("cfg-pdb-comp-wl").value.split("\n").map(function(s){return s.trim()}).filter(Boolean),
        pdb_comp_require_admin:document.getElementById("cfg-pdb-comp-admin").value=="1",
        pdb_comp_blacklist:document.getElementById("cfg-pdb-comp-bl").value.split("\n").map(function(s){return s.trim()}).filter(Boolean),
        pdb_storage_mode:document.getElementById("cfg-pdb-storage-mode").value,
        pdb_read_source:document.getElementById("cfg-pdb-read-source").value,
        pdb_ext_db_path:document.getElementById("cfg-pdb-ext-db-path").value.trim(),
        pdb_ext_host:document.getElementById("cfg-pdb-ext-host").value.trim(),
        pdb_ext_port:parseInt(document.getElementById("cfg-pdb-ext-port").value)||3306,
        pdb_ext_user:document.getElementById("cfg-pdb-ext-user").value.trim(),
        pdb_ext_password:document.getElementById("cfg-pdb-ext-password").value.trim(),
        pdb_ext_database:document.getElementById("cfg-pdb-ext-database").value.trim(),
        tracker_enabled:document.getElementById("cfg-tk-on").value=="1",
        tracker_method:document.getElementById("cfg-tk-method").value,
        tracker_interval:parseInt(document.getElementById("cfg-tk-interval").value)||60,
        tracker_poll_mode:document.getElementById("cfg-tk-poll-mode").value,
        tracker_idle_interval:parseInt(document.getElementById("cfg-tk-idle-int").value)||300,
        tracker_active_interval:parseInt(document.getElementById("cfg-tk-active-int").value)||60,
        ranking_reset_hours:parseInt(document.getElementById("cfg-tk-rank-reset").value)||0,
        log_listener_enabled:document.getElementById("cfg-tk-log-listen").value=="1",
        tk_notify:document.getElementById("cfg-tk-notify").value=="1",
        tk_target:document.getElementById("cfg-tk-target").value,
        tk_intervals:document.getElementById("cfg-tk-intervals").value.split(",").map(function(s){return parseInt(s.trim())}).filter(function(n){return!isNaN(n)}),
        tk_notify_game:document.getElementById("cfg-tk-notify-game").value=="1",
        tk_fmt_game:document.getElementById("cfg-tk-fmt-game").value,
        tk_game_prefix:document.getElementById("cfg-tk-prefix-game").value,
        tk_kick:document.getElementById("cfg-tk-kick").value=="1",
        tk_threshold:parseInt(document.getElementById("cfg-tk-threshold").value)||720,
        tk_ban:parseInt(document.getElementById("cfg-tk-ban").value)||30,
        sq_addr:document.getElementById("cfg-sq-addr").value=="1",
        sq_ver:document.getElementById("cfg-sq-ver").value=="1",
        sq_lat:document.getElementById("cfg-sq-lat").value=="1",
        sq_on:document.getElementById("cfg-sq-on").value=="1",
        sq_pl:document.getElementById("cfg-sq-pl").value=="1",
        sq_img:document.getElementById("cfg-sq-img").value=="1",
        sq_clean:parseInt(document.getElementById("cfg-sq-clean").value)||10,
        relay_enabled:document.getElementById("cfg-relay-on").value=="1",
        relay_group_to_mc:document.getElementById("cfg-relay-g2m").value=="1",
        relay_mc_to_group:document.getElementById("cfg-relay-m2g").value=="1",
        relay_fmt_group:document.getElementById("cfg-relay-fg").value,
        relay_fmt_mc:document.getElementById("cfg-relay-fm").value,
        rcn_persistent:document.getElementById("cfg-rcn-persistent").value=="1",
        scripts_dir:document.getElementById("cfg-scripts-dir").value.trim(),rcon_keepalive_interval:parseInt(document.getElementById("cfg-keepalive-int").value)||180,rcon_idle_disconnect:parseInt(document.getElementById("cfg-idle-disc").value)||0,
        event_macro_game_prefix:document.getElementById("cfg-em-game-prefix").value,
        game_notify_prefix:document.getElementById("cfg-gn-game-prefix").value,
        dangerous_blacklist:document.getElementById("cfg-dangerous").value.split("\n").map(function(s){return s.trim()}).filter(Boolean),
        online_history_max_bars:parseInt(document.getElementById("cfg-tk-max-bars").value)||70,
        log_viewer_refresh_ms:parseInt(document.getElementById("cfg-lv-refresh").value)||10000
    };
    try{await pjt(A+"/config/save",b);toast("设置已保存！可能需要重启插件才能完全生效")}catch(e){toast("保存失败: "+e.message,true)}
    return false
}
/* ====== Idle timeout ====== */
function rstIdle(){var m=d.getElementById("ma");if(!m||m.style.display==="none")return;if(idleT)clearTimeout(idleT);idleT=setTimeout(function(){login("会话已超时，请重新登录")},idleTO*1000)}
function visChg(){if(d.hidden){if(bgT)clearTimeout(bgT);bgT=setTimeout(function(){login("后台时间过长，请重新登录")},idleTO*1000)}else{if(bgT)clearTimeout(bgT);bgT=null;rstIdle()}}
d.addEventListener("mousemove",rstIdle);d.addEventListener("keydown",rstIdle);d.addEventListener("click",rstIdle);d.addEventListener("scroll",rstIdle);d.addEventListener("visibilitychange",visChg);
/* ====== Init ====== */
window.onerror=function(m,s,l,c,e){showErr("JS错误: "+m);return false};
document.querySelectorAll(".sb nav a").forEach(function(a){a.addEventListener("click",function(e){e.preventDefault();nav(a.dataset.tab)})});
window.addEventListener("hashchange",function(){var t=location.hash.slice(1)||"dashboard";if(t!==tab)nav(t)});
setTimeout(function(){
    var l=d.getElementById("login-root");
    if(l&&l.style.display!=="none"){login()}
},5000);
try{chk()}catch(e){console.error("[MRCon] 初始化失败:",e);showErr("连接失败: "+e.message+"<br><small>请按 F12 打开浏览器控制台查看详情</small>")}
</script>
</body>
</html>"""


def _get_panel_version() -> str:
    """从 metadata.yaml 读取插件版本，用于面板显示"""
    try:
        import yaml
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "metadata.yaml")
        with open(p, "r", encoding="utf-8") as f:
            m = yaml.safe_load(f)
            return str(m.get("version", "v3.37.5"))
    except Exception:
        return "v3.37.5"


class WebServer:
    """Web 管理面板 — 原生 asyncio TCP + serve_forever + 密码登录"""

    def __init__(self, plugin, host: str = "0.0.0.0", port: int = 9949, session_timeout: int = 600):
        self.plugin = plugin
        self.host = host
        self.port = port
        self.session_timeout = max(60, session_timeout)
        self._server: Optional[asyncio.AbstractServer] = None
        self._sessions: Dict[str, float] = {}
        self._failed_logins: Dict[str, List[float]] = {}

    # ==================== 生命周期 ====================

    async def run(self):
        """启动并 serve_forever — 由 asyncio.create_task 驱动"""
        original_port = self.port
        last_error = None
        for offset in range(5):
            cp = original_port + offset
            try:
                self._server = await asyncio.start_server(self._handle_client, self.host, cp)
                if offset:
                    logger.warning(f"[mrcon] Web 端口 {original_port} → {cp}")
                    self.port = cp
                    try:
                        self.plugin.config["web_panel"]["port"] = cp
                        self.plugin.config.save_config()
                    except Exception:
                        pass
                break
            except OSError as e:
                last_error = e
                logger.warning(f"[mrcon] Web 端口 {cp} 被占用 → {cp + 1}")
                continue
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"[mrcon] Web 启动失败: {e}")
                return
        if not self._server:
            logger.error(f"[mrcon] Web 端口 {original_port}-{original_port + 4} 绑定失败: {last_error}")
            return
        try:
            sockets = self._server.sockets or []
            if sockets:
                addr = sockets[0].getsockname()
                logger.info(f"[mrcon] Web 管理面板已启动 → http://{addr[0]}:{addr[1]}")
            await self._server.serve_forever()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"[mrcon] Web serve_forever 异常: {e}")
        finally:
            if self._server:
                self._server.close()
                try:
                    await asyncio.wait_for(self._server.wait_closed(), timeout=5)
                except (asyncio.TimeoutError, Exception):
                    pass
                self._server = None

    async def stop(self):
        if self._server:
            self._server.close()
            try:
                await asyncio.wait_for(self._server.wait_closed(), timeout=3)
            except (asyncio.TimeoutError, Exception):
                pass
            self._server = None

    # ==================== 密码管理 ====================

    def is_password_configured(self) -> bool:
        return bool(self.plugin.config.get("webui_password_hash") and
                    self.plugin.config.get("webui_password_salt"))

    def set_password(self, plain: str):
        salt = secrets.token_hex(16)
        self.plugin.config["webui_password_alg"] = "pbkdf2_sha256"
        self.plugin.config["webui_password_iters"] = 200000
        self.plugin.config["webui_password_salt"] = salt
        self.plugin.config["webui_password_hash"] = self._hash_password(plain, salt)
        self.plugin.config.save_config()
        self._sessions.clear()
        self._failed_logins.clear()

    def verify_password(self, plain: str) -> bool:
        if not self.is_password_configured():
            return False
        salt = str(self.plugin.config.get("webui_password_salt", ""))
        expected = str(self.plugin.config.get("webui_password_hash", ""))
        if not salt or not expected:
            return False
        return hmac.compare_digest(expected, self._hash_password(plain, salt))

    def _hash_password(self, password: str, salt: str) -> str:
        iters = int(self.plugin.config.get("webui_password_iters", 0) or 0)
        if iters > 0:
            try:
                salt_bytes = bytes.fromhex(salt)
            except ValueError:
                salt_bytes = salt.encode("utf-8")
            return hashlib.pbkdf2_hmac("sha256", password.encode(), salt_bytes, iters).hex()
        return hashlib.sha256((salt + password).encode()).hexdigest()

    # ==================== Session ====================

    def _prune_sessions(self):
        now = time.time()
        expired = [sid for sid, exp in self._sessions.items() if exp <= now]
        for sid in expired:
            self._sessions.pop(sid, None)

    def _create_session(self) -> str:
        sid = secrets.token_urlsafe(32)
        self._sessions[sid] = time.time() + self.session_timeout
        return sid

    def _check_session(self, cookies: Dict[str, str]) -> bool:
        self._prune_sessions()
        sid = cookies.get("API_SESSION")
        if not sid:
            return False
        expiry = self._sessions.get(sid)
        if not expiry or time.time() >= expiry:
            self._sessions.pop(sid, None)
            return False
        self._sessions[sid] = time.time() + self.session_timeout
        return True

    def _session_cookie(self, sid: str = "") -> str:
        if not sid:
            return "API_SESSION=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"
        # 使用较长的 Max-Age 防止浏览器独立于服务端删除 cookie。
        # 服务端通过 _check_session / _prune_sessions 控制实际过期。
        return f"API_SESSION={sid}; Path=/; HttpOnly; SameSite=Strict; Max-Age=2592000"

    # ==================== HTTP 构造工具 ====================

    def _build(self, status: int, reason: str, content_type: str,
               body: bytes, extra_headers: Dict[str, str] = None) -> bytes:
        headers = [
            f"HTTP/1.1 {status} {reason}",
            f"Content-Type: {content_type}",
            f"Content-Length: {len(body)}",
            "Connection: close",
            "Cache-Control: no-store",
            "X-Content-Type-Options: nosniff",
        ]
        if extra_headers:
            for k, v in extra_headers.items():
                headers.append(f"{k}: {v}")
        headers.extend(["", ""])
        return "\r\n".join(headers).encode("utf-8") + body

    def _html(self, content: str, status: int = 200) -> bytes:
        return self._build(status, "OK", "text/html; charset=utf-8", content.encode("utf-8"))

    def _json(self, data: Any, status: int = 200) -> bytes:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        return self._build(status, "OK", "application/json; charset=utf-8", body)

    def _json_err(self, status: int, msg: str) -> bytes:
        return self._json({"error": msg}, status=status)

    def _raw_bytes(self, body: str | bytes, content_type: str, filename: str = "") -> bytes:
        """返回原始字节响应（用于导出文件）"""
        if isinstance(body, str):
            body = body.encode("utf-8")
        extra = {}
        if filename:
            extra["Content-Disposition"] = f'attachment; filename="{filename}"'
        return self._build(200, "OK", content_type, body, extra_headers=extra)

    def _redirect(self, location: str, extra_headers: Dict[str, str] = None) -> bytes:
        headers = [
            "HTTP/1.1 302 Found",
            f"Location: {location}",
            "Content-Length: 0",
            "Connection: close",
        ]
        if extra_headers:
            for k, v in extra_headers.items():
                headers.append(f"{k}: {v}")
        headers.extend(["", ""])
        return "\r\n".join(headers).encode("utf-8")

    def _json_with_cookie(self, data: Any, sid: str, status: int = 200) -> bytes:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        return self._build(status, "OK", "application/json; charset=utf-8", body,
                           extra_headers={"Set-Cookie": self._session_cookie(sid)})

    # ==================== 请求处理 ====================

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            await asyncio.wait_for(self._handle_request(reader, writer), timeout=30)
        except (asyncio.TimeoutError, ConnectionError, Exception):
            pass
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def _handle_request(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            line = await reader.readline()
            if not line:
                return
            parts = line.decode("utf-8", "ignore").strip().split()
            if len(parts) < 2:
                return
            method, path = parts[0], parts[1]
            logger.info(f"[mrcon] Web 请求 {method} {path}")
            headers: Dict[str, str] = {}
            while True:
                ln = await reader.readline()
                if not ln or ln in (b"\r\n", b"\n"):
                    break
                d = ln.decode("utf-8", "ignore")
                if ":" in d:
                    k, _, v = d.partition(":")
                    headers[k.strip().lower()] = v.strip()
            body = b""
            cl = headers.get("content-length")
            if cl:
                try:
                    n = int(cl)
                    if 0 < n < 10 * 1024 * 1024:
                        body = await reader.readexactly(n)
                except Exception:
                    body = await reader.read(10 * 1024 * 1024)
            cookies = self._parse_cookies(headers.get("cookie", ""))
            resp = await self._dispatch(method, path, headers, body, cookies)
            writer.write(resp)
            await writer.drain()
        except Exception as e:
            import traceback
            logger.error(f"[mrcon] Web 请求失败: {e}\n{traceback.format_exc()}")
            try:
                writer.write(self._json_err(500, str(e)))
                await writer.drain()
            except Exception:
                pass

    def _parse_cookies(self, header: str) -> Dict[str, str]:
        result: Dict[str, str] = {}
        if not header:
            return result
        for item in header.split(";"):
            if "=" in item:
                k, v = item.split("=", 1)
                result[k.strip()] = v.strip()
        return result

    def _read_body(self, body: bytes) -> dict:
        try:
            return json.loads(body) if body else {}
        except Exception:
            return {}

    async def _dispatch(self, method: str, path: str, headers: Dict[str, str],
                         body: bytes, cookies: Dict[str, str]) -> bytes:
        p = urlparse(path)
        route = p.path
        params = parse_qs(p.query)

        # ---------- MC→群消息转发（无需认证，内部 API） ----------
        if route == "/api/mc_relay" and method == "POST":
            return await self._api_mc_relay(body, params)

        # ---------- 登录/登出/首页/静态资源（无需认证） ----------
        if route == "/" or route == "":
            return self._html(PANEL_HTML.replace("v3.37.5", _get_panel_version()))
        if route == "/api/login" and method == "POST":
            return await self._handle_login(body)
        if route == "/api/logout" and method == "POST":
            return self._handle_logout(cookies)
        if route == "/api/auth":
            if not self.is_password_configured() or self._check_session(cookies):
                return self._json({"ok": True})
            return self._json_err(401, "unauthorized")

        # ---------- 如果没有设置密码，直接放行 ----------
        if self.is_password_configured() and not self._check_session(cookies):
            return self._json_err(401, "unauthorized")

        # ---------- 仪表盘 ----------
        if route == "/api/status":
            return self._api_status()

        # ---------- 群 / 服务器 ----------
        if route == "/api/groups":
            return self._api_groups(params)
        if route == "/api/servers":
            return await self._api_add_server(body) if method == "POST" else self._api_servers()
        if route.startswith("/api/servers/") and route.count("/") >= 4:
            parts_r = route.split("/")
            gid = parts_r[3]
            try: idx = int(parts_r[4])
            except (ValueError, IndexError): return self._json_err(400, "bad idx")
            if method == "GET": return self._api_get_server(gid, idx)
            if method == "PUT": return await self._api_update_server(gid, idx, body)
            if method == "DELETE": return self._api_del_server(gid, idx)
            return self._json_err(405, "")

        # ---------- Relay ----------
        if route == "/api/relay/all":
            return self._api_relay_all()
        if route.startswith("/api/relay/") and route.count("/") == 3:
            gid = route.split("/")[3]
            if method == "GET": return self._api_relay_get(gid)
            if method == "PUT": return await self._api_relay_set(gid, body)
            if method == "POST": return await self._api_relay_add(gid, body)
            if method == "DELETE": return self._api_relay_reset(gid)
        if route.startswith("/api/relay/") and route.count("/") == 4:
            parts = route.split("/")
            gid, idx = parts[3], int(parts[4])
            if method == "DELETE": return self._api_relay_del_entry(gid, idx)

        # ---------- Tracker ----------
        if route == "/api/tracker/all":
            return self._api_tracker_all()
        if route.startswith("/api/tracker/") and route.count("/") == 3:
            gid = route.split("/")[3]
            if method == "GET": return self._api_tracker_get(gid)
            if method == "PUT": return await self._api_tracker_set(gid, body)
            if method == "DELETE": return self._api_tracker_reset(gid)

        # ---------- 配置 ----------
        if route == "/api/config/relay":
            if method == "PUT": return await self._api_config_relay_set(body)
            return self._api_config_relay()
        if route == "/api/config/tracker":
            if method == "PUT": return await self._api_config_tracker_set(body)
            return self._api_config_tracker()
        if route == "/api/config/all": return self._api_config_all()
        if route == "/api/config/save" and method == "PUT": return await self._api_save_config(body)

        # ---------- 配置中的群聊与服务器列表（供模板等选择） ----------
        if route == "/api/config-servers":
            return self._json({
                "servers": self.plugin.config.get("servers", []),
                "groups": self.plugin.config.get("groups", []),
                "group_names": self.plugin.config.get("group_names", {}),
            })

        # ---------- 服务器配置模板 ----------
        if route == "/api/server-templates":
            if method == "GET": return self._api_list_templates()
            if method == "POST": return await self._api_add_template(body)
        if route.startswith("/api/server-templates/") and route.count("/") == 3:
            tpl_name = unquote(route.split("/")[3])
            if method == "PUT": return await self._api_update_template(tpl_name, body)
            if method == "DELETE": return self._api_delete_template(tpl_name)

        # ---------- 群名称 ----------
        if route == "/api/group-names":
            if method == "GET": return self._api_list_group_names()
        if route.startswith("/api/group-names/") and route.count("/") == 3:
            gn_gid = route.split("/")[3]
            if method == "PUT": return await self._api_set_group_name(gn_gid, body)
            if method == "DELETE": return self._api_delete_group_name(gn_gid)

        # ---------- 参数化命令模板 ----------
        if route == "/api/cmd-templates":
            if method == "GET": return self._api_list_cmd_tpls()
            if method == "POST": return await self._api_add_cmd_tpl(body)
        if route.startswith("/api/cmd-templates/") and route.count("/") == 3:
            ct_name = unquote(route.split("/")[3])
            if method == "PUT": return await self._api_update_cmd_tpl(ct_name, body)
            if method == "DELETE": return self._api_delete_cmd_tpl(ct_name)

        # ---------- 上线触发器 ----------
        if route == "/api/online-triggers":
            if method == "GET": return self._api_list_ot()
            if method == "POST": return await self._api_add_ot(body)
        if route.startswith("/api/online-triggers/") and route.count("/") == 3:
            ot_name = unquote(route.split("/")[3])
            if method == "PUT": return await self._api_update_ot(ot_name, body)
            if method == "DELETE": return self._api_delete_ot(ot_name)

        # ---------- RCON 命令执行 ----------
        if route == "/api/rcon/exec" and method == "POST":
            return await self._api_rcon_exec(body)

        # ---------- 玩家 ----------
        if route == "/api/players":
            if method == "GET": return self._api_players(params)
            if method == "POST": return await self._api_add_player(body)
        if route == "/api/players/import_online" and method == "POST":
            return await self._api_import_online(params)
        if route.startswith("/api/players/") and route.count("/") == 3:
            qq_id = route.split("/")[3]
            if method == "PUT": return await self._api_update_player(qq_id, body)
            if method == "DELETE": return self._api_delete_player(qq_id)

        # ---------- 补偿 ----------
        if route == "/api/compensations":
            return self._api_compensations(params)
        if route == "/api/compensations/count":
            return self._api_compensations_count(params)
        if route.startswith("/api/compensations/") and route.endswith("/approve"):
            try: return self._api_comp_approve(int(route.split("/")[3]))
            except (ValueError, IndexError): return self._json_err(400, "")
        if route.startswith("/api/compensations/") and route.endswith("/reject"):
            try: return self._api_comp_reject(int(route.split("/")[3]))
            except (ValueError, IndexError): return self._json_err(400, "")

        # ---------- 积分兑换 ----------
        if route == "/api/exchange":
            return self._api_exchange_all(params)
        if route.startswith("/api/exchange/"):
            parts = route.split("/")
            gid = parts[3]
            if len(parts) == 4:
                if method == "GET": return self._api_exchange_get(gid)
                if method == "POST": return await self._api_exchange_add(gid, body)
            if len(parts) == 5:
                try:
                    eid = int(parts[4])
                    if method == "PUT": return await self._api_exchange_update(gid, eid, body)
                    if method == "DELETE": return self._api_exchange_delete(gid, eid)
                except ValueError: return self._json_err(400, "")

        # ---------- 抽奖 ----------
        if route == "/api/lottery":
            return self._api_lottery_all(params)
        if route.startswith("/api/lottery/"):
            parts = route.split("/")
            gid = parts[3]
            if len(parts) == 4:
                if method == "GET": return self._api_lottery_get(gid)
                if method == "POST": return await self._api_lottery_add(gid, body)
            if len(parts) == 5:
                try:
                    pid = int(parts[4])
                    if method == "PUT": return await self._api_lottery_update(gid, pid, body)
                    if method == "DELETE": return self._api_lottery_delete(gid, pid)
                except ValueError: return self._json_err(400, "")

        # ---------- 在线 ----------
        if route == "/api/online":
            return self._api_online(params)
        if route == "/api/online/refresh":
            if method == "POST": return await self._api_online_refresh()
            return self._json_err(405, "POST only")
        if route == "/api/online_history":
            limit = int(params.get("limit", ["50"])[0])
            return self._api_online_history(limit)
        if route == "/api/online_ranking":
            limit = int(params.get("limit", ["20"])[0])
            return self._api_online_ranking(limit)
        if route == "/api/online_ranking/reset" and method == "POST":
            return self._api_online_ranking_reset()

        # ---------- 审计 ----------
        if route == "/api/audit":
            limit = int(params.get("limit", ["100"])[0])
            offset = int(params.get("offset", ["0"])[0])
            category = params.get("category", [""])[0]
            keyword = params.get("keyword", [""])[0]
            event_type = params.get("event_type", [""])[0]
            server_name = params.get("server_name", [""])[0]
            time_from = int(params.get("time_from", ["0"])[0])
            time_to = int(params.get("time_to", ["0"])[0])
            ok = params.get("ok", [None])[0]
            if ok is not None:
                ok = ok.lower() in ("1", "true")
            return self._api_audit_search(limit, offset, category, event_type, server_name, keyword, ok, time_from, time_to)
        if route == "/api/audit/export":
            fmt = params.get("format", ["json"])[0]
            keyword = params.get("keyword", [""])[0]
            category = params.get("category", [""])[0]
            event_type = params.get("event_type", [""])[0]
            time_from = int(params.get("time_from", ["0"])[0])
            time_to = int(params.get("time_to", ["0"])[0])
            return self._api_audit_export(fmt, keyword, category, event_type, time_from, time_to)
        if route == "/api/audit/delete" and method == "POST":
            return self._api_audit_delete(body)

        # ---------- 宏 ----------
        if route == "/api/macros":
            return await self._api_add_macro(body) if method == "POST" else self._api_macros()
        if route.startswith("/api/macros/") and route.count("/") == 3:
            mn = unquote(route.split("/")[3])
            if method == "PUT": return await self._api_update_macro(mn, body)
            if method == "DELETE": return self._api_del_macro(mn)

        # ---------- 脚本 ----------
        if route == "/api/scripts":
            return await self._api_add_script(body) if method == "POST" else self._api_scripts()
        if route.startswith("/api/scripts/") and route.count("/") == 3:
            sc_name = unquote(route.split("/")[3])
            if method == "PUT": return await self._api_toggle_script(sc_name, body)
            if method == "DELETE": return self._api_del_script(sc_name)

        # ---------- 快捷命令设置 ----------
        if route == "/api/quick-cmd-settings":
            if method == "GET": return self._api_quick_cmd_settings()
        if route.startswith("/api/quick-cmd-settings/") and route.count("/") == 3:
            qc_name = unquote(route.split("/")[3])
            if method == "PUT": return await self._api_toggle_quick_cmd(qc_name, body)
        # ---------- 快捷命令配置（读写命令定义） ----------
        if route == "/api/quick-cmds/config":
            if method == "GET": return self._api_quick_cmds_config()
            if method == "PUT": return self._api_save_quick_cmds_config(body)
        # ---------- 自定义命令映射 ----------
        if route.startswith("/api/custom-cmds/") and route.count("/") == 4:
            parts = route.split("/")
            cmds_gid = unquote(parts[3])
            cmds_idx = int(parts[4])
            if method == "PUT": return await self._api_update_custom_cmd(cmds_gid, cmds_idx, body)
            if method == "DELETE": return self._api_del_custom_cmd(cmds_gid, cmds_idx)
        if route == "/api/custom-cmds":
            if method == "GET": return self._api_custom_cmds(params)
            if method == "POST": return await self._api_add_custom_cmd(body)

        # ---------- 事件宏 ----------
        if route == "/api/event-macros":
            if method == "GET": return self._api_event_macros()
            if method == "POST": return await self._api_event_macro_save(body)
        if route == "/api/event-macros/export" and method == "GET":
            return self._api_event_macros_export()
        if route == "/api/event-macros/import" and method == "POST":
            return await self._api_event_macros_import(body)
        if route.startswith("/api/event-macros/") and route.count("/") == 3:
            try:
                idx = int(route.split("/")[3])
                if method == "PUT": return await self._api_event_macro_save(body, idx)
                if method == "DELETE": return self._api_event_macro_delete(idx)
            except ValueError:
                pass

        # ---------- 日志查看器 ----------
        if route == "/api/log-viewer/recent":
            return self._api_log_viewer_recent(params)
        if route == "/api/log-viewer/servers":
            return self._api_log_viewer_servers()
        if route == "/api/log-viewer/log-path" and method == "PUT":
            return await self._api_log_viewer_set_log_path(body)
        if route == "/api/log-viewer/test":
            return self._api_log_viewer_test(params)

        return self._json_err(404, "not found")

    # ==================== Auth 处理 ====================

    async def _handle_login(self, body: bytes) -> bytes:
        if not self.is_password_configured():
            sid = self._create_session()
            return self._json_with_cookie({"ok": True}, sid)
        data = self._read_body(body)
        pwd = str(data.get("password", ""))
        if not pwd:
            return self._json_err(400, "missing password")
        if not self.verify_password(pwd):
            return self._json_err(403, "wrong password")
        sid = self._create_session()
        return self._json_with_cookie({"ok": True}, sid)

    def _handle_logout(self, cookies: Dict[str, str]) -> bytes:
        sid = cookies.get("API_SESSION")
        if sid:
            self._sessions.pop(sid, None)
        return self._json_with_cookie({"ok": True}, "")

    # ==================== 仪表盘 ====================

    def _api_status(self) -> bytes:
        p = self.plugin
        sc = sum(len(v) for v in p.group_servers.values())
        on = len(p._online_cache) if hasattr(p, '_online_cache') else 0
        return self._json({
            "group_count": len(p.group_servers),
            "server_count": sc,
            "player_count": p.db.count_players() if hasattr(p.db, 'count_players') else 0,
            "online_count": on,
            "admin_count": len(p.admin_qqs),
            "macro_count": len(p.macros),
            "script_count": len(os.listdir(p.scripts_dir)) if os.path.isdir(p.scripts_dir) else 0,
            "relay_enabled": p.relay_enabled,
            "relay_fmt": p.relay_fmt_group,
            "tracker_enabled": p.tracker_enabled,
            "tracker_interval": p.tracker_interval,
            "kick_threshold": p.tracker_kick_threshold,
            "pdb_enabled": p.pdb_enabled,
            "checkin_pts": p.pdb_checkin_pts,
            "comp_enabled": p.pdb_comp_enabled,
            "rate_enabled": p.rate_enabled,
            "rate_base": p.rate_base_ms,
            "rate_threshold": p.rate_threshold,
            "dangerous_count": len(p.dangerous_blacklist),
            "dangerous_list": p.dangerous_blacklist[:8],
        })

    # ==================== 群 / 服务器 API ====================

    def _api_groups(self, params=None) -> bytes:
        result: Dict[str, list] = {}
        filter_wm = (params or {}).get("filter_web_mgmt", [""])[0] == "1"
        for gid, srvs in self.plugin.group_servers.items():
            if filter_wm:
                # 有任意一台服务器开启 web 管理时，此群才可见
                if not any(s.get("web_management_enabled", True) for s in srvs):
                    logger.info(
                        f"[mrcon] _api_groups 过滤群 {gid}: "
                        f"所有 {len(srvs)} 台服务器 web_mgmt 均为 false"
                    )
                    continue
            result[gid] = [{k: v for k, v in s.items() if k not in ("rcon_password",)}
                           for s in srvs]
        logger.info(
            f"[mrcon] _api_groups filter_wm={filter_wm} "
            f"返回 {len(result)} 个群, keys={list(result.keys())}"
        )
        return self._json(result)

    def _is_group_web_managed(self, gid: str) -> bool:
        """群内至少有一台服务器开启了 web 管理"""
        srvs = self.plugin.group_servers.get(str(gid), [])
        return any(s.get("web_management_enabled", True) for s in srvs)

    def _api_servers(self) -> bytes:
        return self._json(list(self.plugin.group_servers.keys()))

    async def _api_add_server(self, body: bytes) -> bytes:
        data = self._read_body(body)
        gid = str(data.get("group_id", "")).strip()
        if not gid:
            return self._json_err(400, "missing group_id")
        name = str(data.get("name", "")).strip()
        if not name:
            return self._json_err(400, "missing name")
        conf = {
            "server_name": name,
            "display_name": name,
            "rcon_host": str(data.get("rcon_host", "")),
            "rcon_port": str(data.get("rcon_port", "25575")),
            "rcon_password": str(data.get("rcon_password", "")),
            "game_port": str(data.get("game_port", "25565")),
            "whitelist_qqs": data.get("whitelist_qqs", []) or [],
            "public_commands": data.get("public_commands", []) or [],
            "relay_enabled": bool(data.get("relay_enabled", False)),
            "query_enabled": bool(data.get("query_enabled", True)),
            "web_management_enabled": bool(data.get("web_management_enabled", True)),
            "vote_enabled": bool(data.get("vote_enabled", False)),
            "vote_threshold": int(data.get("vote_threshold", 3) or 3),
            "vote_ttl": int(data.get("vote_ttl", 60) or 60),
            "vote_min_agree_on_timeout": int(data.get("vote_min_agree_on_timeout", 1) or 1),
            "vote_tie_strategy": str(data.get("vote_tie_strategy", "fail")),
            "admin_decide_ttl": int(data.get("admin_decide_ttl", 120) or 120),
            "log_path": str(data.get("log_path", "")),
            "log_mode": str(data.get("log_mode", "")),
            "log_paths": data.get("log_paths", []) or [],
            "log_folder": str(data.get("log_folder", "")),
            "log_file_pattern": str(data.get("log_file_pattern", "latest.log")),
        }
        self.plugin.group_servers.setdefault(gid, []).append(conf)
        self.plugin.group_map[gid] = conf
        self._save_config()
        return self._json(conf, status=201)

    def _api_get_server(self, gid: str, idx: int) -> bytes:
        srvs = self.plugin.group_servers.get(gid, [])
        if idx < 0 or idx >= len(srvs):
            return self._json_err(404, "server not found")
        s = srvs[idx]
        return self._json({k: v for k, v in s.items()})

    async def _api_update_server(self, gid: str, idx: int, body: bytes) -> bytes:
        srvs = self.plugin.group_servers.get(gid, [])
        if idx < 0 or idx >= len(srvs):
            return self._json_err(404, "server not found")
        data = self._read_body(body)
        s = srvs[idx]
        for field in ("server_name", "name", "display_name", "rcon_host", "rcon_port",
                       "rcon_password", "game_port", "log_path", "log_mode", "log_folder",
                       "log_file_pattern"):
            if field in data:
                s[field] = str(data[field])
        if "name" in data:
            s["server_name"] = s["display_name"] = str(data["name"])
        for field in ("relay_enabled", "query_enabled", "web_management_enabled", "vote_enabled"):
            if field in data:
                s[field] = bool(data[field])
        logger.info(
            f"[mrcon] _api_update_server gid={gid} idx={idx} "
            f"web_management_enabled={s.get('web_management_enabled')} "
            f"total_groups={len(self.plugin.group_servers)}"
        )
        for field in ("vote_threshold", "vote_ttl", "vote_min_agree_on_timeout", "admin_decide_ttl"):
            if field in data:
                s[field] = int(data[field] or 0)
        for list_field in ("whitelist_qqs", "public_commands", "log_paths"):
            if list_field in data:
                s[list_field] = data[list_field] if isinstance(data[list_field], list) else []
        if "vote_tie_strategy" in data:
            s["vote_tie_strategy"] = str(data["vote_tie_strategy"])
        self._save_config()
        return self._json({k: v for k, v in s.items()})

    def _api_del_server(self, gid: str, idx: int) -> bytes:
        srvs = self.plugin.group_servers.get(gid, [])
        if idx < 0 or idx >= len(srvs):
            return self._json_err(404, "server not found")
        srvs.pop(idx)
        if not srvs:
            self.plugin.group_servers.pop(gid, None)
            self.plugin.group_map.pop(gid, None)
        else:
            self.plugin.group_map[gid] = srvs[0]
        self._save_config()
        return self._json({"ok": True})

    # ==================== Relay API ====================

    def _norm_relay(self, ov: dict) -> dict:
        """规范化 relay overrides：单条目 dict → [dict] 列表"""
        out = {}
        for gid, val in ov.items():
            if isinstance(val, dict):
                out[gid] = [val] if val else []
            elif isinstance(val, list):
                out[gid] = val
            else:
                out[gid] = []
        return out

    def _api_relay_all(self) -> bytes:
        return self._json(self._norm_relay(getattr(self.plugin, '_relay_overrides', {})))

    async def _api_mc_relay(self, body: bytes, params: dict) -> bytes:
        """POST /api/mc_relay — MC 服插件推送聊天消息到 QQ 群"""
        data = self._read_body(body)
        server_name = data.get("server", "") or params.get("server", [""])[0]
        player = data.get("player", "")
        msg = data.get("msg", "")
        if not server_name or not player or not msg:
            return self._json_err(400, "missing server/player/msg")
        count = await self.plugin._on_mc_chat(server_name, player, msg)
        logger.info(f"[mrcon] MC→群 relay: server={server_name} player={player} groups={count}")
        return self._json({"ok": True, "groups": count})

    def _api_relay_get(self, gid: str) -> bytes:
        ov = self._norm_relay(getattr(self.plugin, '_relay_overrides', {}))
        return self._json(ov.get(gid, []))

    async def _api_relay_set(self, gid: str, body: bytes) -> bytes:
        """PUT: 替换某群的 relay 条目列表（或单条目向后兼容）"""
        data = self._read_body(body)
        ov = self._norm_relay(getattr(self.plugin, '_relay_overrides', {}))
        if isinstance(data, dict):
            entries = [data]
        elif isinstance(data, list):
            entries = data
        else:
            return self._json_err(400, "invalid relay data")
        ov[gid] = entries
        self.plugin._relay_overrides = ov
        self.plugin._save_relay_overrides()
        return self._json(entries)

    async def _api_relay_add(self, gid: str, body: bytes) -> bytes:
        """POST: 新增一条 relay 条目"""
        data = self._read_body(body)
        if not isinstance(data, dict) or "server_name" not in data:
            return self._json_err(400, "missing server_name")
        ov = self._norm_relay(getattr(self.plugin, '_relay_overrides', {}))
        entry = {
            "server_name": data.get("server_name", ""),
            "group_to_mc": data.get("group_to_mc", True),
            "mc_to_group": data.get("mc_to_group", True),
            "enabled": data.get("enabled", True),
        }
        ov.setdefault(gid, []).append(entry)
        self.plugin._relay_overrides = ov
        self.plugin._save_relay_overrides()
        return self._json(entry)

    def _api_relay_del_entry(self, gid: str, idx: int) -> bytes:
        """DELETE: 删除某群的指定条目"""
        ov = self._norm_relay(getattr(self.plugin, '_relay_overrides', {}))
        entries = ov.get(gid, [])
        if 0 <= idx < len(entries):
            entries.pop(idx)
            if not entries:
                ov.pop(gid, None)
            else:
                ov[gid] = entries
            self.plugin._relay_overrides = ov
        self.plugin._save_relay_overrides()
        return self._json({"ok": True})

    def _api_relay_reset(self, gid: str) -> bytes:
        ov = getattr(self.plugin, '_relay_overrides', {})
        ov.pop(gid, None)
        self.plugin._relay_overrides = ov
        self.plugin._save_relay_overrides()
        return self._json({"ok": True})

    # ==================== Tracker API ====================

    def _api_tracker_all(self) -> bytes:
        ov = getattr(self.plugin, '_tracker_overrides', {})
        logger.debug(f"[mrcon] _api_tracker_all 返回 {len(ov)} 个群覆盖: {list(ov.keys())}")
        return self._json(ov)

    def _api_tracker_get(self, gid: str) -> bytes:
        return self._json(getattr(self.plugin, '_tracker_overrides', {}).get(gid, {}))

    async def _api_tracker_set(self, gid: str, body: bytes) -> bytes:
        data = self._read_body(body)
        ov = getattr(self.plugin, '_tracker_overrides', {})
        entry = ov.setdefault(gid, {})
        mapping = {
            "use_global": True, "notify_enabled": True,
            "notify_intervals": True, "notify_in_game": True,
            "kick_enabled": True, "kick_threshold": True,
            "ban_minutes": True, "ban_cmd": True, "kick_reason": True, "duration_mode": True,
            "mention_mode": True, "mention_format": True,
        }
        for k, v in data.items():
            if k in mapping:
                entry[k] = v
        self.plugin._tracker_overrides = ov
        # 持久化（JSON 文件 + config）
        self.plugin._save_tracker_overrides()
        logger.debug(f"[mrcon] tracker覆盖已保存 gid={gid} use_global={entry.get('use_global')} keys={list(entry.keys())}")
        return self._json(entry)

    def _api_tracker_reset(self, gid: str) -> bytes:
        ov = getattr(self.plugin, '_tracker_overrides', {})
        ov.pop(gid, None)
        self.plugin._tracker_overrides = ov
        # 持久化（JSON 文件 + config）
        self.plugin._save_tracker_overrides()
        return self._json({"ok": True})

    # ==================== 配置 API ====================

    def _api_config_relay(self) -> bytes:
        p = self.plugin
        rc = p.config.get("relay", {})
        return self._json({
            "relay_enabled": p.relay_enabled,
            "relay_group_to_mc": p.relay_group_to_mc,
            "relay_mc_to_group": p.relay_mc_to_group,
            "relay_mc_to_group_log": p.relay_mc_to_group_log,
            "relay_require_msay": p.relay_require_msay,
            "relay_fmt_group": p.relay_fmt_group,
            "relay_fmt_mc": p.relay_fmt_mc,
            "relay_fmt_mc_log": getattr(p, "relay_fmt_mc_log", ""),
        })

    async def _api_config_relay_set(self, body: bytes) -> bytes:
        """PUT: 更新全局 relay 配置"""
        data = self._read_body(body)
        p = self.plugin
        rc = p.config.setdefault("relay", {})
        bool_map = {"relay_enabled": "relay_enabled", "relay_group_to_mc": "relay_group_to_mc", "relay_mc_to_group": "relay_mc_to_group", "relay_mc_to_group_log": "relay_mc_to_group_log", "relay_require_msay": "relay_require_msay"}
        for k, attr in bool_map.items():
            if k in data:
                rc[k] = bool(data[k])
                setattr(p, attr, rc[k])
        str_map = {"relay_fmt_group": "relay_fmt_group", "relay_fmt_mc": "relay_fmt_mc", "relay_fmt_mc_log": "relay_fmt_mc_log"}
        for k, attr in str_map.items():
            if k in data:
                rc[k] = str(data[k])
                setattr(p, attr, rc[k])
        p.config["relay"] = rc
        return self._json({"ok": True})

    def _api_config_tracker(self) -> bytes:
        p = self.plugin
        return self._json({
            "tracker_enabled": p.tracker_enabled,
            "tracker_notify": p.tracker_notify,
            "tracker_notify_intervals": p.tracker_notify_intervals,
            "tracker_notify_game": p.tracker_notify_game,
            "tracker_kick_enabled": p.tracker_kick_enabled,
            "tracker_kick_threshold": p.tracker_kick_threshold,
            "tracker_ban_minutes": p.tracker_ban_minutes,
            "tracker_ban_cmd": p.tracker_ban_cmd,
            "tracker_duration_mode": p.tracker_duration_mode,
            "tracker_mention_mode": p.tracker_notify_mention_mode,
            "tracker_mention_format": p.tracker_notify_mention_format,
            "ranking_reset_hours": p.ranking_reset_hours,
        })

    async def _api_config_tracker_set(self, body: bytes) -> bytes:
        """PUT: 更新全局追踪配置"""
        data = self._read_body(body)
        p = self.plugin
        tc = p.config.setdefault("online_tracker", {})
        # 前端属性名 → config.yaml 键名映射
        bool_map = {
            "tracker_enabled": "enabled",
            "tracker_notify": "notify_enabled",
            "tracker_notify_game": "notify_in_game",
            "tracker_kick_enabled": "auto_kick_enabled",
        }
        int_map = {
            "tracker_kick_threshold": "auto_kick_threshold",
            "tracker_ban_minutes": "ban_minutes",
        }
        for attr, cfg_key in bool_map.items():
            if attr in data:
                tc[cfg_key] = bool(data[attr])
                setattr(p, attr, bool(data[attr]))
        for attr, cfg_key in int_map.items():
            if attr in data:
                tc[cfg_key] = int(data[attr])
                setattr(p, attr, int(data[attr]))
        if "tracker_notify_intervals" in data:
            val = data["tracker_notify_intervals"]
            if isinstance(val, list):
                tc["notify_intervals"] = sorted([int(x) for x in val], reverse=True)
            else:
                tc["notify_intervals"] = sorted([int(x) for x in str(val).split(",") if x.strip().isdigit()], reverse=True)
            p.tracker_notify_intervals = tc["notify_intervals"]
        if "ranking_reset_hours" in data:
            tc["ranking_reset_interval_hours"] = int(data["ranking_reset_hours"])
            p.ranking_reset_hours = int(data["ranking_reset_hours"])
        if "tracker_duration_mode" in data:
            tc["duration_mode"] = str(data["tracker_duration_mode"])
            p.tracker_duration_mode = str(data["tracker_duration_mode"])
        if "tracker_ban_cmd" in data:
            v = str(data["tracker_ban_cmd"]).strip()
            tc["auto_kick_ban_cmd"] = v
            p.tracker_ban_cmd = v
        if "tracker_mention_mode" in data:
            tc["notify_mention_mode"] = str(data["tracker_mention_mode"])
            p.tracker_notify_mention_mode = str(data["tracker_mention_mode"])
        if "tracker_mention_format" in data:
            tc["notify_mention_format"] = str(data["tracker_mention_format"])
            p.tracker_notify_mention_format = str(data["tracker_mention_format"])
        # 保留 group_overrides（如果已在 tc 中）
        if "group_overrides" not in tc:
            ov = getattr(p, '_tracker_overrides', {})
            if ov:
                tc["group_overrides"] = ov
        p.config["online_tracker"] = tc
        try:
            p.config.save_config()
        except Exception as e:
            logger.warning(f"[mrcon] 保存全局追踪配置失败: {e}")
        return self._json({"ok": True})

    def _api_config_all(self) -> bytes:
        p = self.plugin
        qc = p.config.get("query", {})
        rc = p.config.get("relay", {})
        tc = p.config.get("online_tracker", {})
        pdb = p.config.get("player_db", {})
        odb = p.config.get("online_db", {})
        gc = p.config.get("general", {})
        return self._json({
            "admin_qqs": list(p.admin_qqs),
            "rcon_timeout": p.config.get("admin", {}).get("rcon_timeout", 5),
            "select_ttl": p.select_ttl,
            # rate limit
            "rate_enabled": p.rate_enabled,
            "rate_base_ms": p.rate_base_ms,
            "rate_window_s": p.rate_window_s,
            "rate_threshold": p.rate_threshold,
            "rate_increment_ms": p.rate_increment_ms,
            "rate_max_ms": p.rate_max_ms,
            "rate_auto_recovery": p.rate_auto_recovery,
            "rate_recovery_s": p.rate_recovery_s,
            "rate_whitelist": list(p.rate_whitelist),
            "rate_whitelist_min_delay_ms": p.rate_whitelist_min_delay_ms,
            # player db
            "pdb_enabled": p.pdb_enabled,
            "pdb_checkin_pts": p.pdb_checkin_pts,
            "pdb_streak_bonus": pdb.get("checkin_streak_bonus", 2),
            "pdb_new_pts": pdb.get("new_player_points", 50),
            "pdb_max_checkin_streak": pdb.get("max_streak", 30),
            "pdb_comp_enabled": p.pdb_comp_enabled,
            "pdb_comp_cooldown_hours": pdb.get("compensation_cooldown_hours", 24),
            "pdb_comp_whitelist": pdb.get("compensation_whitelist", []),
            "pdb_comp_require_admin": pdb.get("compensation_require_admin", True),
            "pdb_comp_blacklist": pdb.get("compensation_blacklist", []),
            # player db storage (优先 player_db，回退 online_db)
            "pdb_storage_mode": str(pdb.get("storage_mode") or odb.get("storage_mode", "local") or "local"),
            "pdb_read_source": str(pdb.get("read_source") or odb.get("read_source", "local") or "local"),
            "pdb_ext_db_path": str(pdb.get("external_db_path") or odb.get("external_db_path", "") or ""),
            "pdb_ext_host": str(pdb.get("external_host") or odb.get("external_host", "") or ""),
            "pdb_ext_port": int(pdb.get("external_port") or odb.get("external_port", 3306) or 3306),
            "pdb_ext_user": str(pdb.get("external_user") or odb.get("external_user", "") or ""),
            "pdb_ext_password": str(pdb.get("external_password") or odb.get("external_password", "") or ""),
            "pdb_ext_database": str(pdb.get("external_database") or odb.get("external_database", "") or ""),
            # tracker (all fields)
            "tracker_enabled": tc.get("enabled", False),
            "tracker_method": tc.get("query_method", "rcon"),
            "tracker_interval": tc.get("poll_interval_seconds", 60),
            "tracker_poll_mode": tc.get("poll_mode", "frequent"),
            "tracker_idle_interval": tc.get("poll_idle_interval_seconds", 300),
            "tracker_active_interval": tc.get("poll_active_interval_seconds", 60),
            "ranking_reset_hours": tc.get("ranking_reset_interval_hours", 0),
            "log_listener_enabled": tc.get("log_listener_enabled", False),
            "log_patterns": tc.get("log_patterns", {}),
            "online_history_max_bars": tc.get("online_history_max_bars", 70),
            "tracker_notify": tc.get("notify_enabled", False),
            "tracker_notify_target": tc.get("notify_target", "group"),
            "tracker_notify_intervals": tc.get("notify_intervals", []),
            "tracker_notify_game": tc.get("notify_in_game", False),
            "tracker_notify_game_fmt": tc.get("notify_game_format", ""),
            "tracker_notify_game_prefix": tc.get("notify_game_prefix", "§e[在线提醒]"),
            "tracker_kick_enabled": tc.get("auto_kick_enabled", False),
            "tracker_kick_threshold": tc.get("auto_kick_threshold", 720),
            "tracker_kick_reason": tc.get("auto_kick_reason", ""),
            "tracker_ban_minutes": tc.get("auto_kick_ban_minutes", 30),
            # relay (full config)
            "relay_enabled": rc.get("enabled", False),
            "relay_group_to_mc": rc.get("group_to_mc", True),
            "relay_mc_to_group": rc.get("mc_to_group", False),
            "relay_mc_to_group_log": rc.get("mc_to_group_log", False),
            "relay_fmt_group": rc.get("format_group", ""),
            "relay_fmt_mc": rc.get("format_mc", ""),
            # query display
            "show_addr_port": qc.get("show_address_port", True),
            "show_ver": qc.get("show_version", True),
            "show_lat": qc.get("show_latency", True),
            "show_on": qc.get("show_online_count", True),
            "show_pl": qc.get("show_players_detail", True),
            "render_img": qc.get("render_online_image", False),
            "auto_cleanup_days": qc.get("auto_cleanup_days", 10),
            # general
            "rcn_persistent": gc.get("rcn_persistent", True),
            "rcon_keepalive_interval": gc.get("rcon_keepalive_interval", 180),
            "rcon_idle_disconnect": gc.get("rcon_idle_disconnect", 0),
            "scripts_dir": gc.get("scripts_dir", "scripts"),
            "event_macro_game_prefix": gc.get("event_macro_game_prefix", "§b[宏]"),
            "game_notify_prefix": gc.get("game_notify_prefix", "§6[通知]"),
            # audit
            "audit_auto_enabled": getattr(p, "audit_auto_enabled", True),
            "audit_skip_categories": getattr(p, "audit_skip_categories", []),
            "audit_db_enabled": getattr(p, "audit_db_enabled", True),
            "audit_retention_days": getattr(p, "audit_retention_days", 90),
            "audit_jsonl_enabled": getattr(p, "audit_jsonl_keep", True),
            # dangerous
            "dangerous_blacklist": p.dangerous_blacklist,
            # online db
            "online_db_storage_mode": str(odb.get("storage_mode", "local") or "local"),
            "online_db_read_source": str(odb.get("read_source", "local") or "local"),
            "online_db_ext_path": str(odb.get("external_db_path", "") or ""),
            # web
            "log_viewer_refresh_ms": self.plugin.log_viewer_refresh_ms,
        })

    # ==================== 玩家 API ====================

    def _api_players(self, params: Dict[str, list]) -> bytes:
        search = params.get("search", [None])[0]
        limit = int(params.get("limit", ["200"])[0])
        db = self.plugin.db
        if hasattr(db, 'get_all_players'):
            rows = db.get_all_players(limit)
        elif hasattr(db, 'cursor'):
            cursor = db.cursor()
            try:
                cursor.execute("""SELECT p.qq_id, p.mc_id, p.points, p.checkin_streak, p.last_checkin_date,
                                    p.first_login, p.last_login, p.created_at, p.vip_level,
                                    COALESCE(SUM(s.end_ts - s.start_ts), 0) / 60 AS total_online_min
                                FROM players p
                                LEFT JOIN online_sessions s ON s.player_name = p.mc_id AND p.mc_id != ''
                                GROUP BY p.qq_id
                                ORDER BY p.created_at DESC LIMIT ?""", (limit,))
                rows = []
                cols = [d[0] for d in cursor.description]
                for row in cursor.fetchall():
                    rows.append(dict(zip(cols, row)))
            finally:
                cursor.close()
        else:
            rows = []
        if search and rows:
            s = search.lower()
            rows = [r for r in rows if s in str(r.get('qq_id', '')) or s in str(r.get('mc_id', '')).lower()]
        return self._json(rows)

    async def _api_add_player(self, body: bytes) -> bytes:
        data = self._read_body(body)
        qq_id = str(data.get("qq_id", "")).strip()
        mc_id = str(data.get("mc_id", "")).strip()
        points = int(data.get("points", 50))
        if not qq_id:
            return self._json_err(400, "missing qq_id")
        db = self.plugin.db
        now = int(time.time())
        if hasattr(db, 'add_player'):
            db.add_player(qq_id, mc_id=mc_id if mc_id else None, points=points, created_at=now)
        elif hasattr(db, 'cursor'):
            conn = db.cursor().connection
            try:
                cur = conn.cursor()
                cur.execute("INSERT INTO players (qq_id, mc_id, points, checkin_streak, created_at) VALUES (?, ?, ?, 0, ?)",
                           (qq_id, mc_id if mc_id else None, points, now))
                conn.commit()
            finally:
                conn.close()
        return self._json({"ok": True, "qq_id": qq_id}, status=201)

    async def _api_update_player(self, qq_id: str, body: bytes) -> bytes:
        data = self._read_body(body)
        db = self.plugin.db
        mc_id = str(data.get("mc_id", "")).strip()
        points = int(data.get("points", 0))
        checkin_streak = int(data.get("checkin_streak", 0))
        vip_level = min(max(int(data.get("vip_level", 0)), 0), 3)
        new_qq_id = str(data.get("new_qq_id", "")).strip()
        upd = {"mc_id": mc_id if mc_id else None, "points": points, "checkin_streak": checkin_streak, "vip_level": vip_level}
        if new_qq_id and new_qq_id != qq_id:
            upd["qq_id"] = new_qq_id
        if hasattr(db, 'update_player'):
            db.update_player(qq_id, upd)
            ok = True
        elif hasattr(db, 'cursor'):
            conn = db.cursor().connection
            try:
                cur = conn.cursor()
                cur.execute("UPDATE players SET mc_id=?, points=?, checkin_streak=? WHERE qq_id=?",
                            (mc_id if mc_id else None, points, checkin_streak, str(qq_id)))
                conn.commit()
                ok = cur.rowcount > 0
            finally:
                conn.close()
        else:
            return self._json_err(500, "db not available")
        if ok:
            self.plugin._audit_web("player_edit", f"QQ={qq_id} MC={mc_id} pts={points}" + (f" →newQQ={new_qq_id}" if new_qq_id and new_qq_id != qq_id else ""))
        return self._json({"ok": ok}) if ok else self._json_err(404, "player not found")

    def _api_delete_player(self, qq_id: str) -> bytes:
        db = self.plugin.db
        if hasattr(db, 'delete_player'):
            ok = db.delete_player(qq_id)
        elif hasattr(db, 'cursor'):
            conn = db.cursor().connection
            try:
                cur = conn.cursor()
                cur.execute("DELETE FROM players WHERE qq_id = ?", (str(qq_id),))
                conn.commit()
                ok = cur.rowcount > 0
            finally:
                conn.close()
        else:
            return self._json_err(500, "db not available")
        if ok:
            self.plugin._audit_web("player_del", f"QQ={qq_id}")
        return self._json({"ok": ok}) if ok else self._json_err(404, "player not found")

    async def _api_import_online(self, params) -> bytes:
        imported = 0
        db = self.plugin.db
        now = int(time.time())
        cache = self.plugin._online_cache
        seen = set()
        for sid, info in cache.items():
            name = info.get("player", "")
            if not name or name in seen:
                continue
            seen.add(name)
            existing = db.find_player_by_mc_id(name)
            if not existing:
                # 使用 _imported_ + 玩家名 作为唯一 qq_id，避免所有导入玩家共用 "0" 导致 INSERT OR IGNORE 静默跳过
                if db.insert_player_raw("_imported_" + name, name, 50, now):
                    imported += 1
        self.plugin._audit_web("player_import", f"imported={imported} total_online={len(seen)}")
        return self._json({"ok": True, "imported": imported, "total_online": len(seen)})

    async def _api_save_config(self, body: bytes) -> bytes:
        data = self._read_body(body)
        p = self.plugin
        cfg = p.config
        # 管理员
        if "admin_qqs" in data:
            cfg["admin"]["admin_qqs"] = [str(q).strip() for q in data["admin_qqs"] if str(q).strip()]
            p.admin_qqs = set(cfg["admin"]["admin_qqs"])
        if "rcon_timeout" in data:
            cfg["admin"]["rcon_timeout"] = int(data["rcon_timeout"])
        if "select_ttl" in data:
            p.select_ttl = int(data["select_ttl"])
        # 速率限制
        rl = cfg.setdefault("rate_limit", {})
        if "rate_enabled" in data:
            rl["enabled"] = bool(data["rate_enabled"])
            p.rate_enabled = rl["enabled"]
        if "rate_base_ms" in data:
            rl["base_ms"] = int(data["rate_base_ms"])
            p.rate_base_ms = rl["base_ms"]
        if "rate_window_minutes" in data:
            rl["window_minutes"] = int(data["rate_window_minutes"])
            p.rate_window_s = rl["window_minutes"] * 60
        if "rate_threshold" in data:
            rl["threshold"] = int(data["rate_threshold"])
            p.rate_threshold = rl["threshold"]
        if "rate_increment_ms" in data:
            rl["increment_ms"] = int(data["rate_increment_ms"])
            p.rate_increment_ms = rl["increment_ms"]
        if "rate_max_ms" in data:
            rl["max_ms"] = int(data["rate_max_ms"])
            p.rate_max_ms = rl["max_ms"]
        if "rate_auto_recovery" in data:
            rl["auto_recovery"] = bool(data["rate_auto_recovery"])
            p.rate_auto_recovery = rl["auto_recovery"]
        if "rate_recovery_minutes" in data:
            rl["recovery_minutes"] = int(data["rate_recovery_minutes"])
            p.rate_recovery_s = rl["recovery_minutes"] * 60
        if "rate_whitelist_qqs" in data:
            rl["whitelist_qqs"] = [str(s).strip() for s in (data["rate_whitelist_qqs"] or []) if str(s).strip()]
            p.rate_whitelist = set(rl["whitelist_qqs"])
        if "rate_whitelist_min_delay_ms" in data:
            rl["whitelist_min_delay_ms"] = max(200, int(data.get("rate_whitelist_min_delay_ms", 200) or 200))
            p.rate_whitelist_min_delay_ms = rl["whitelist_min_delay_ms"]
        # 玩家数据库
        pdb = cfg.setdefault("player_db", {})
        if "pdb_enabled" in data:
            pdb["enabled"] = bool(data["pdb_enabled"])
            p.pdb_enabled = pdb["enabled"]
        if "pdb_checkin_pts" in data:
            pdb["checkin_points"] = int(data["pdb_checkin_pts"])
            p.pdb_checkin_pts = pdb["checkin_points"]
        if "pdb_streak_bonus" in data:
            pdb["streak_bonus"] = int(data["pdb_streak_bonus"])
        if "pdb_new_pts" in data:
            pdb["new_player_points"] = int(data["pdb_new_pts"])
        if "pdb_comp_enabled" in data:
            pdb["compensation_enabled"] = bool(data["pdb_comp_enabled"])
            p.pdb_comp_enabled = pdb["compensation_enabled"]
        if "pdb_comp_cooldown_hours" in data:
            pdb["compensation_cooldown_hours"] = int(data["pdb_comp_cooldown_hours"])
        if "pdb_comp_whitelist" in data:
            pdb["compensation_whitelist"] = list(data["pdb_comp_whitelist"])
        if "pdb_comp_require_admin" in data:
            pdb["compensation_require_admin"] = bool(data["pdb_comp_require_admin"])
        if "pdb_comp_blacklist" in data:
            pdb["compensation_blacklist"] = list(data["pdb_comp_blacklist"])
        # player db 存储配置
        if "pdb_storage_mode" in data:
            pdb["storage_mode"] = str(data["pdb_storage_mode"])
        if "pdb_read_source" in data:
            pdb["read_source"] = str(data["pdb_read_source"])
        if "pdb_ext_db_path" in data:
            pdb["external_db_path"] = str(data["pdb_ext_db_path"])
        if "pdb_ext_host" in data:
            pdb["external_host"] = str(data["pdb_ext_host"])
        if "pdb_ext_port" in data:
            pdb["external_port"] = int(data["pdb_ext_port"])
        if "pdb_ext_user" in data:
            pdb["external_user"] = str(data["pdb_ext_user"])
        if "pdb_ext_password" in data:
            pdb["external_password"] = str(data["pdb_ext_password"])
        if "pdb_ext_database" in data:
            pdb["external_database"] = str(data["pdb_ext_database"])
        # 同步存储配置到 online_db (兼容)
        odb = cfg.setdefault("online_db", {})
        for k in ("storage_mode", "read_source", "external_db_path",
                   "external_host", "external_port", "external_user",
                   "external_password", "external_database"):
            if k in pdb:
                odb[k] = pdb[k]
        # General
        gc = cfg.setdefault("general", {})
        if "rcn_persistent" in data:
            gc["rcn_persistent"] = bool(data["rcn_persistent"])
            p.rcn_persistent = gc["rcn_persistent"]
        if "rcon_keepalive_interval" in data:
            gc["rcon_keepalive_interval"] = int(data["rcon_keepalive_interval"])
            p.rcon_keepalive_interval = gc["rcon_keepalive_interval"]
            if p.rcn_persistent:
                get_pool().configure(keepalive_interval=p.rcon_keepalive_interval)
        if "rcon_idle_disconnect" in data:
            gc["rcon_idle_disconnect"] = int(data["rcon_idle_disconnect"])
            p.rcon_idle_disconnect = gc["rcon_idle_disconnect"]
            if p.rcn_persistent:
                get_pool().configure(idle_disconnect=p.rcon_idle_disconnect)
        if "scripts_dir" in data:
            gc["scripts_dir"] = str(data["scripts_dir"])
        if "event_macro_game_prefix" in data:
            gc["event_macro_game_prefix"] = str(data["event_macro_game_prefix"])
            p.event_macro_game_prefix = gc["event_macro_game_prefix"]
        if "game_notify_prefix" in data:
            gc["game_notify_prefix"] = str(data["game_notify_prefix"])
            p.game_notify_prefix = gc["game_notify_prefix"]
        # 持久化通用前缀到独立 JSON 文件
        if "event_macro_game_prefix" in data or "game_notify_prefix" in data:
            p._save_general_overrides()
        # 在线追踪 (full fields)
        tc = cfg.setdefault("online_tracker", {})
        if "tracker_enabled" in data:
            tc["enabled"] = bool(data["tracker_enabled"])
            p.tracker_enabled = tc["enabled"]
        if "tracker_method" in data:
            tc["query_method"] = str(data["tracker_method"])
        if "tracker_interval" in data:
            tc["poll_interval_seconds"] = int(data["tracker_interval"])
        if "tracker_poll_mode" in data:
            tc["poll_mode"] = str(data["tracker_poll_mode"])
            p.tracker_poll_mode = tc["poll_mode"]
        if "tracker_idle_interval" in data:
            tc["poll_idle_interval_seconds"] = int(data["tracker_idle_interval"])
            p.tracker_idle_interval = tc["poll_idle_interval_seconds"]
        if "tracker_active_interval" in data:
            tc["poll_active_interval_seconds"] = int(data["tracker_active_interval"])
            p.tracker_active_interval = tc["poll_active_interval_seconds"]
        if "ranking_reset_hours" in data:
            tc["ranking_reset_interval_hours"] = int(data["ranking_reset_hours"])
            p.ranking_reset_hours = tc["ranking_reset_interval_hours"]
        if "log_listener_enabled" in data:
            tc["log_listener_enabled"] = bool(data["log_listener_enabled"])
        if "online_history_max_bars" in data:
            tc["online_history_max_bars"] = int(data["online_history_max_bars"])
            p.online_history_max_bars = tc["online_history_max_bars"]
        if "log_viewer_refresh_ms" in data:
            wc = cfg.setdefault("web_panel", {})
            wc["log_viewer_refresh_ms"] = int(data["log_viewer_refresh_ms"])
            p.log_viewer_refresh_ms = wc["log_viewer_refresh_ms"]
        if "tk_notify" in data:
            tc["notify_enabled"] = bool(data["tk_notify"])
        if "tk_target" in data:
            tc["notify_target"] = str(data["tk_target"])
        if "tk_intervals" in data:
            tc["notify_intervals"] = data["tk_intervals"] if isinstance(data["tk_intervals"], list) else []
            p.tracker_notify_intervals = tc["notify_intervals"]
        if "tk_notify_game" in data:
            tc["notify_in_game"] = bool(data["tk_notify_game"])
        if "tk_fmt_game" in data:
            tc["notify_game_format"] = str(data["tk_fmt_game"])
        if "tk_game_prefix" in data:
            tc["notify_game_prefix"] = str(data["tk_game_prefix"])
        if "tk_kick" in data:
            tc["auto_kick_enabled"] = bool(data["tk_kick"])
            p.tracker_kick_enabled = tc["auto_kick_enabled"]
        if "tk_threshold" in data:
            tc["auto_kick_threshold"] = int(data["tk_threshold"])
            p.tracker_kick_threshold = tc["auto_kick_threshold"]
        if "tk_reason" in data:
            tc["auto_kick_reason"] = str(data["tk_reason"])
        if "tk_ban" in data:
            tc["auto_kick_ban_minutes"] = int(data["tk_ban"])
            p.tracker_ban_minutes = tc["auto_kick_ban_minutes"]
        # 日志监听
        if "log_listener_enabled" in data:
            p.log_listener_enabled = bool(data["log_listener_enabled"])
        if "log_patterns" in data:
            lp = data["log_patterns"]
            if isinstance(lp, str):
                import json as _json
                try:
                    lp = _json.loads(lp)
                except Exception:
                    lp = {}
            if isinstance(lp, dict):
                tc["log_patterns"] = lp
                p._log_listener.reload_patterns(lp)
        # Query display
        qc = cfg.setdefault("query", {})
        for k_map in [("sq_addr", "show_address_port"), ("sq_ver", "show_version"),
                      ("sq_lat", "show_latency"), ("sq_on", "show_online_count"),
                      ("sq_pl", "show_players_detail"), ("sq_img", "render_online_image")]:
            if k_map[0] in data:
                qc[k_map[1]] = bool(data[k_map[0]])
        if "sq_clean" in data:
            qc["auto_cleanup_days"] = int(data["sq_clean"])
        # Relay full config
        rc = cfg.setdefault("relay", {})
        if "relay_enabled" in data:
            rc["enabled"] = bool(data["relay_enabled"])
            p.relay_enabled = rc["enabled"]
        if "relay_group_to_mc" in data:
            rc["group_to_mc"] = bool(data["relay_group_to_mc"])
            p.relay_group_to_mc = rc["group_to_mc"]
        if "relay_mc_to_group" in data:
            rc["mc_to_group"] = bool(data["relay_mc_to_group"])
            p.relay_mc_to_group = rc["mc_to_group"]
        if "relay_mc_to_group_log" in data:
            rc["mc_to_group_log"] = bool(data["relay_mc_to_group_log"])
            p.relay_mc_to_group_log = rc["mc_to_group_log"]
        if "relay_fmt_group" in data:
            rc["format_group"] = str(data["relay_fmt_group"])
            p.relay_fmt_group = rc["format_group"]
        if "relay_fmt_mc" in data:
            rc["format_mc"] = str(data["relay_fmt_mc"])
        # 危险命令黑名单
        if "dangerous_blacklist" in data:
            cfg["dangerous_commands"] = [str(c).strip() for c in data["dangerous_blacklist"] if str(c).strip()]
            p.dangerous_blacklist = cfg["dangerous_commands"]
        # 审计
        if "audit_auto_enabled" in data:
            ac = cfg.setdefault("audit", {})
            ac["auto_enabled"] = bool(data["audit_auto_enabled"])
            p.audit_auto_enabled = ac["auto_enabled"]
        if "audit_skip_categories" in data:
            ac = cfg.setdefault("audit", {})
            ac["skip_categories"] = list(data["audit_skip_categories"]) if isinstance(data["audit_skip_categories"], list) else []
            p.audit_skip_categories = ac["skip_categories"]
        if "audit_db_enabled" in data:
            ac = cfg.setdefault("audit", {})
            ac["db_enabled"] = bool(data["audit_db_enabled"])
            p.audit_db_enabled = ac["db_enabled"]
        if "audit_retention_days" in data:
            ac = cfg.setdefault("audit", {})
            ac["retention_days"] = int(data["audit_retention_days"]) if data["audit_retention_days"] else 90
            p.audit_retention_days = ac["retention_days"]
        if "audit_jsonl_enabled" in data:
            ac = cfg.setdefault("audit", {})
            ac["jsonl_enabled"] = bool(data["audit_jsonl_enabled"])
            p.audit_jsonl_keep = ac["jsonl_enabled"]
        # 在线数据库
        odb = cfg.setdefault("online_db", {})
        if "online_db_storage_mode" in data:
            odb["storage_mode"] = str(data["online_db_storage_mode"])
        if "online_db_read_source" in data:
            odb["read_source"] = str(data["online_db_read_source"])
        if "online_db_ext_path" in data:
            odb["external_db_path"] = str(data["online_db_ext_path"])
        try:
            cfg.save_config()
        except Exception as e:
            return self._json_err(500, f"save failed: {e}")
        self.plugin._audit_web("config_save", "配置已更新")
        return self._json({"ok": True, "msg": "配置已保存"})

    # ==================== RCON 命令执行 ====================

    async def _api_rcon_exec(self, body: bytes) -> bytes:
        data = self._read_body(body)
        group_id = str(data.get("group_id", ""))
        if not group_id:
            return self._json_err(400, "missing group_id")

        # 支持批量 commands 数组格式
        commands = data.get("commands", [])
        if not isinstance(commands, list) or not commands:
            # 兼容旧版单条 command 格式
            command = str(data.get("command", ""))
            if not command:
                return self._json_err(400, "missing command or commands")
            commands = [command]

        server_index = int(data.get("server_index", 0))
        srvs = self.plugin.group_servers.get(group_id, [])
        if server_index < 0 or server_index >= len(srvs):
            return self._json_err(404, "server not found")
        s = srvs[server_index]

        results = []
        for cmd in commands:
            cmd = str(cmd)
            if not cmd.strip():
                continue
            try:
                resp = await self.plugin._rcn_send(s["rcon_host"], int(s["rcon_port"]), s["rcon_password"], cmd)
                self.plugin._audit_web_cmd(f"RCON: {cmd}", resp[:200], True)
                results.append({"cmd": cmd, "ok": True, "reply": resp})
            except Exception as e:
                self.plugin._audit_web_cmd(f"RCON: {cmd}", str(e)[:200], False)
                results.append({"cmd": cmd, "ok": False, "error": str(e)})
        return self._json({"ok": True, "results": results})

    # ==================== 补偿 API ====================

    def _api_compensations(self, params: Dict[str, list]) -> bytes:
        status = params.get("status", ["pending"])[0]
        limit = int(params.get("limit", ["100"])[0])
        db = self.plugin.db
        if hasattr(db, 'get_all_compensations'):
            rows = db.get_all_compensations(status if status != "all" else None, limit)
        elif hasattr(db, 'cursor'):
            cursor = db.cursor()
            try:
                if status == "all":
                    cursor.execute("SELECT * FROM compensations ORDER BY time DESC LIMIT ?", (limit,))
                else:
                    cursor.execute("SELECT * FROM compensations WHERE status=? ORDER BY time DESC LIMIT ?", (status, limit))
                rows = []
                cols = [d[0] for d in cursor.description]
                for row in cursor.fetchall():
                    rows.append(dict(zip(cols, row)))
            finally:
                cursor.close()
        else:
            rows = []
        return self._json(rows)

    def _api_compensations_count(self, params: Dict[str, list]) -> bytes:
        db = self.plugin.db
        counts = {"all": 0, "pending": 0, "approved": 0, "rejected": 0}
        if hasattr(db, 'count_compensations'):
            counts["pending"] = db.count_compensations("pending")
            counts["approved"] = db.count_compensations("approved")
            counts["rejected"] = db.count_compensations("rejected")
            counts["all"] = counts["pending"] + counts["approved"] + counts["rejected"]
        elif hasattr(db, 'cursor'):
            cursor = db.cursor()
            try:
                for s in ("pending", "approved", "rejected"):
                    cursor.execute("SELECT COUNT(*) FROM compensations WHERE status=?", (s,))
                    counts[s] = cursor.fetchone()[0]
                counts["all"] = counts["pending"] + counts["approved"] + counts["rejected"]
            finally:
                cursor.close()
        return self._json({"count": counts.get("pending", 0), **counts})

    def _api_comp_approve(self, comp_id: int) -> bytes:
        db = self.plugin.db
        if hasattr(db, 'update_compensation'):
            db.update_compensation(comp_id, "approved")
        elif hasattr(db, 'cursor'):
            cursor = db.cursor()
            try:
                cursor.execute("UPDATE compensations SET status='approved' WHERE id=?", (comp_id,))
                db.connection.commit()
            finally:
                cursor.close()
        return self._json({"ok": True})

    def _api_comp_reject(self, comp_id: int) -> bytes:
        db = self.plugin.db
        if hasattr(db, 'update_compensation'):
            db.update_compensation(comp_id, "rejected")
        elif hasattr(db, 'cursor'):
            cursor = db.cursor()
            try:
                cursor.execute("UPDATE compensations SET status='rejected' WHERE id=?", (comp_id,))
                db.connection.commit()
            finally:
                cursor.close()
        return self._json({"ok": True})

    # ==================== 积分兑换 API ====================

    def _api_exchange_all(self, params: Dict[str, list]) -> bytes:
        gid = params.get("gid", [""])[0]
        items = self.plugin.db.get_exchange_items(gid)
        return self._json(items)

    def _api_exchange_get(self, gid: str) -> bytes:
        items = self.plugin.db.get_exchange_items(gid)
        return self._json(items)

    async def _api_exchange_add(self, gid: str, body: bytes) -> bytes:
        data = self._read_body(body)
        name = str(data.get("name", "")).strip()
        desc = str(data.get("description", "")).strip()
        rcon_cmd = str(data.get("rcon_cmd", "")).strip()
        cost = int(data.get("cost_points", 0))
        if not name or not rcon_cmd or cost <= 0:
            return self._json_err(400, "名称、RCON命令和积分消耗不能为空")
        eid = self.plugin.db.add_exchange_item(gid, name, desc, rcon_cmd, cost)
        self.plugin._audit_web("exchange_add", f"gid={gid} name={name} cost={cost}")
        return self._json({"ok": True, "id": eid})

    async def _api_exchange_update(self, gid: str, eid: int, body: bytes) -> bytes:
        data = self._read_body(body)
        upd = {}
        for k in ["name", "description", "rcon_cmd"]:
            if k in data:
                upd[k] = str(data[k]).strip()
        if "cost_points" in data:
            upd["cost_points"] = int(data["cost_points"])
        if "enabled" in data:
            upd["enabled"] = 1 if data["enabled"] else 0
        if upd:
            self.plugin.db.update_exchange_item(eid, upd)
            self.plugin._audit_web("exchange_edit", f"eid={eid}")
        return self._json({"ok": True})

    def _api_exchange_delete(self, gid: str, eid: int) -> bytes:
        self.plugin.db.delete_exchange_item(eid)
        self.plugin._audit_web("exchange_del", f"eid={eid}")
        return self._json({"ok": True})

    # ==================== 抽奖 API ====================

    def _api_lottery_all(self, params: Dict[str, list]) -> bytes:
        gid = params.get("gid", [""])[0]
        items = self.plugin.db.get_all_lottery_prizes(gid)
        return self._json(items)

    def _api_lottery_get(self, gid: str) -> bytes:
        items = self.plugin.db.get_all_lottery_prizes(gid)
        return self._json(items)

    async def _api_lottery_add(self, gid: str, body: bytes) -> bytes:
        data = self._read_body(body)
        name = str(data.get("name", "")).strip()
        desc = str(data.get("description", "")).strip()
        prob = float(data.get("probability", 0.1))
        count = int(data.get("count", 1))
        rcon_cmd = str(data.get("rcon_cmd", "")).strip()
        cost = int(data.get("cost_points", 10))
        if not name or not rcon_cmd:
            return self._json_err(400, "名称和RCON命令不能为空")
        pid = self.plugin.db.add_lottery_prize(gid, name, desc, prob, count, rcon_cmd, cost)
        self.plugin._audit_web("lottery_add", f"gid={gid} name={name}")
        return self._json({"ok": True, "id": pid})

    async def _api_lottery_update(self, gid: str, pid: int, body: bytes) -> bytes:
        data = self._read_body(body)
        upd = {}
        for k in ["name", "description", "rcon_cmd"]:
            if k in data:
                upd[k] = str(data[k]).strip()
        for k in ["probability", "count", "cost_points"]:
            if k in data:
                upd[k] = float(data[k]) if k == "probability" else int(data[k])
        if "enabled" in data:
            upd["enabled"] = 1 if data["enabled"] else 0
        if upd:
            self.plugin.db.update_lottery_prize(pid, upd)
            self.plugin._audit_web("lottery_edit", f"pid={pid}")
        return self._json({"ok": True})

    def _api_lottery_delete(self, gid: str, pid: int) -> bytes:
        self.plugin.db.delete_lottery_prize(pid)
        self.plugin._audit_web("lottery_del", f"pid={pid}")
        return self._json({"ok": True})

    # ==================== 在线 API ====================

    def _api_online(self, params: dict = None) -> bytes:
        cache: dict = getattr(self.plugin, '_online_cache', {}) or {}
        now = int(time.time())
        filter_gid = None
        if params:
            fg = params.get("gid", [""])[0].strip()
            if fg:
                filter_gid = fg
        result: Dict[str, dict] = {}
        for sid, data in cache.items():
            if not isinstance(data, dict):
                continue
            gid = str(data.get("gid", ""))
            if gid and not self._is_group_web_managed(gid):
                continue
            server_name = data.get("server", data.get("server_name", sid))
            player = data.get("player", sid)
            if not player:
                continue
            if filter_gid and gid != filter_gid:
                continue
            login_at = data.get("login_at", 0)
            session_secs = int(now - login_at) if login_at else 0
            result.setdefault(server_name, {})
            result[server_name][player] = {
                "login_at": login_at,
                "session_minutes": session_secs // 60,
                "server_name": server_name,
                "gid": gid,
            }
        return self._json({
            "online": result,
        })

    async def _api_online_refresh(self) -> bytes:
        """POST: 触发 RCON 查询刷新在线缓存，有 30 秒冷却"""
        p = self.plugin
        now = int(time.time())
        cooldown = 30
        if p._last_online_refresh > 0 and now - p._last_online_refresh < cooldown:
            remaining = cooldown - (now - p._last_online_refresh)
            return self._json_err(429, f"刷新过于频繁，请 {remaining} 秒后再试")
        p._last_online_refresh = now
        all_servers = []
        for gid, srvs in p.group_servers.items():
            if not self._is_group_web_managed(gid):
                continue
            for srv in srvs:
                all_servers.append((gid, srv))
        servers_ok = 0
        servers_err = 0
        total_found = 0
        for gid, conf in all_servers:
            if not conf.get("query_enabled", True):
                continue
            try:
                online = await p._get_online_player_list(conf)
                srv_name = conf.get("server_name", "unknown")
                total_found += len(online)
                for player in online:
                    sid = f"{srv_name}:{player}"
                    if sid not in p._online_cache:
                        p._online_cache[sid] = {
                            "login_at": now, "player": player, "server": srv_name,
                            "gid": gid, "notified": set(), "kicked": False,
                        }
                        # 自动将新在线玩家录入数据库
                        try:
                            existing = p.db.find_player_by_mc_id(player)
                            if not existing:
                                if p._is_valid_player_name(player):
                                    p.db.insert_player_raw("_imported_" + player, player, 50, now)
                        except Exception:
                            pass
                # 清理该服务器已下线玩家
                for sid in list(p._online_cache.keys()):
                    entry = p._online_cache[sid]
                    if entry.get("server") == srv_name and entry.get("player") not in online:
                        del p._online_cache[sid]
                servers_ok += 1
            except Exception:
                servers_err += 1
                continue
        return self._json({
            "ok": True,
            "servers_ok": servers_ok,
            "servers_err": servers_err,
            "total_found": total_found,
            "cache_size": len(p._online_cache),
        })

    def _api_online_history(self, limit: int = 50) -> bytes:
        db = self.plugin.db
        rows = []
        if hasattr(db, 'get_online_sessions'):
            rows = db.get_online_sessions(limit)
            for d in rows:
                start_ts = d.get("start_ts", 0)
                end_ts = d.get("end_ts", 0)
                d["start_fmt"] = time.strftime("%m/%d %H:%M", time.localtime(start_ts))
                d["end_fmt"] = time.strftime("%m/%d %H:%M", time.localtime(end_ts))
                d["minutes"] = (end_ts - start_ts) / 60 if end_ts > start_ts else 0
        elif hasattr(db, '_connect'):
            conn = db._connect()
            try:
                cur = conn.cursor()
                cur.execute(
                    "SELECT player_name, server_name, start_ts, end_ts FROM online_sessions ORDER BY start_ts DESC LIMIT ?", (limit,))
                cols = [d[0] for d in cur.description]
                for row in cur.fetchall():
                    d = dict(zip(cols, row))
                    start_ts = d.get("start_ts", 0)
                    end_ts = d.get("end_ts", 0)
                    d["start_fmt"] = time.strftime("%m/%d %H:%M", time.localtime(start_ts))
                    d["end_fmt"] = time.strftime("%m/%d %H:%M", time.localtime(end_ts))
                    d["minutes"] = (end_ts - start_ts) / 60 if end_ts > start_ts else 0
                    rows.append(d)
            finally:
                conn.close()
        return self._json(rows)

    def _api_online_ranking(self, limit: int) -> bytes:
        db = self.plugin.db
        rows = []
        if hasattr(db, 'get_online_time_ranking'):
            rows = db.get_online_time_ranking(limit)
        elif hasattr(db, 'cursor'):
            cursor = db.cursor()
            try:
                cursor.execute(
                    "SELECT server_name, player_name, SUM(session_seconds) as total FROM online_sessions "
                    "GROUP BY server_name, player_name ORDER BY total DESC LIMIT ?", (limit,))
                cols = [d[0] for d in cursor.description]
                for row in cursor.fetchall():
                    rows.append(dict(zip(cols, row)))
            finally:
                cursor.close()
        return self._json(rows)

    def _api_online_ranking_reset(self) -> bytes:
        """POST: 重置在线时长排行（清空 sessions 表）"""
        p = self.plugin
        now = int(time.time())
        cooldown = 60
        if p._last_online_refresh > 0 and now - p._last_online_refresh < cooldown:
            remaining = cooldown - (now - p._last_online_refresh)
            return self._json_err(429, f"操作过于频繁，请 {remaining} 秒后再试")
        db = p.db
        if hasattr(db, '_connect'):
            conn = db._connect()
            try:
                cur = conn.cursor()
                cur.execute("DELETE FROM online_sessions")
                conn.commit()
                count = cur.rowcount
            finally:
                conn.close()
            p._audit_web("ranking_reset", f"已清空 {count} 条在线记录")
            return self._json({"ok": True, "deleted": count})
        return self._json_err(500, "db not available")

    # ==================== 审计 API ====================

    def _api_audit_search(self, limit: int, offset: int, category: str = "",
                          event_type: str = "", server_name: str = "",
                          keyword: str = "", ok: bool | None = None,
                          time_from: int = 0, time_to: int = 0) -> bytes:
        """审计日志搜索（优先 DB，回退 JSONL）"""
        p = self.plugin
        # 优先走数据库
        if getattr(p, "audit_db_enabled", False):
            try:
                entries, total = p.db.search_audit_logs(
                    limit=limit, offset=offset,
                    category=category, event_type=event_type,
                    server_name=server_name, keyword=keyword,
                    ok=ok, time_from=time_from, time_to=time_to,
                )
                for e in entries:
                    e["ok"] = bool(e["ok"])
                return self._json({"entries": entries, "total": total})
            except Exception:
                pass
        # 回退 JSONL
        af = getattr(p, "audit_file", None)
        if not af or not os.path.exists(af):
            return self._json({"entries": [], "total": 0})
        entries = []
        with open(af, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if category and entry.get("category", "cmd") != category:
                    continue
                if event_type and entry.get("event_type", "") != event_type:
                    continue
                if server_name and entry.get("server_name", "") != server_name:
                    continue
                if keyword:
                    kw = keyword.lower()
                    if kw not in (entry.get("cmd","")+entry.get("resp","")+entry.get("sender_name","")+entry.get("event_type","")).lower():
                        continue
                if ok is not None and bool(entry.get("ok", True)) != ok:
                    continue
                if time_from > 0 and int(entry.get("time", 0)) < time_from:
                    continue
                if time_to > 0 and int(entry.get("time", 0)) > time_to:
                    continue
                entries.append(entry)
        total = len(entries)
        entries.sort(key=lambda x: x.get("time", 0), reverse=True)
        entries = entries[offset:offset + limit]
        return self._json({"entries": entries, "total": total})

    def _api_audit_export(self, fmt: str = "json", keyword: str = "",
                          category: str = "", event_type: str = "",
                          time_from: int = 0, time_to: int = 0) -> bytes:
        """导出审计日志"""
        p = self.plugin
        entries = []
        # 优先从 DB 导出
        if getattr(p, "audit_db_enabled", False):
            try:
                entries, _ = p.db.search_audit_logs(
                    limit=50000, offset=0,
                    category=category, event_type=event_type,
                    keyword=keyword, time_from=time_from, time_to=time_to,
                )
            except Exception:
                pass
        # 否则从 JSONL 读取
        if not entries:
            af = getattr(p, "audit_file", None)
            if af and os.path.exists(af):
                with open(af, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if category and entry.get("category", "cmd") != category:
                            continue
                        if event_type and entry.get("event_type", "") != event_type:
                            continue
                        if keyword:
                            kw = keyword.lower()
                            if kw not in (entry.get("cmd","")+entry.get("resp","")+entry.get("sender_name","")).lower():
                                continue
                        if time_from > 0 and int(entry.get("time", 0)) < time_from:
                            continue
                        if time_to > 0 and int(entry.get("time", 0)) > time_to:
                            continue
                        entries.append(entry)
                entries.sort(key=lambda x: x.get("time", 0), reverse=True)
        if fmt == "csv":
            header = "\uFEFF" + "时间,类型,事件,QQ号,昵称,群聊,操作,结果,详情\n"
            rows = []
            for e in entries:
                t = datetime.fromtimestamp(e.get("time", 0)).strftime("%Y-%m-%d %H:%M:%S")
                ok_text = "成功" if e.get("ok", True) else "失败"
                row = f'"{t}","{e.get("category","")}","{e.get("event_type","")}",'
                row += f'"{e.get("sender_id","")}","{e.get("sender_name","")}","{e.get("group_id","")}",'
                row += f'"{e.get("cmd","")}","{ok_text}","{e.get("resp","")}"'
                rows.append(row)
            return self._raw_bytes(header + "\n".join(rows), "text/csv; charset=utf-8", "audit_logs.csv")
        else:
            return self._raw_bytes(json.dumps(entries, ensure_ascii=False, indent=2),
                                   "application/json; charset=utf-8", "audit_logs.json")

    def _api_audit_delete(self, body: bytes) -> bytes:
        """批量删除审计日志（按 ID 或按时间范围）"""
        p = self.plugin
        try:
            data = json.loads(body)
        except Exception:
            return self._json_err(400, "无效的 JSON")
        ids = data.get("ids", [])
        before_ts = data.get("before_ts", 0)
        if not getattr(p, "audit_db_enabled", False):
            return self._json_err(400, "审计数据库未启用")
        try:
            if ids and isinstance(ids, list):
                deleted = p.db.delete_audit_logs_by_ids([int(i) for i in ids])
            elif before_ts:
                deleted = p.db.delete_audit_logs_before(int(before_ts))
            else:
                return self._json_err(400, "缺少 ids 或 before_ts 参数")
            return self._json({"deleted": deleted})
        except Exception as e:
            return self._json_err(500, str(e))

    # ==================== 宏 API ====================

    def _api_macros(self) -> bytes:
        return self._json(self.plugin.macros)

    async def _api_add_macro(self, body: bytes) -> bytes:
        data = self._read_body(body)
        name = str(data.get("name", "")).strip()
        commands = data.get("commands", [])
        if not name or not commands:
            return self._json_err(400, "missing name or commands")
        self.plugin.macros[name] = {
            "commands": [str(c) for c in commands],
            "enabled": bool(data.get("enabled", True)),
        }
        self._save_macros()
        self.plugin._audit_web("macro_add", f"name={name}")
        return self._json({"name": name, "commands": self.plugin.macros[name]["commands"], "enabled": self.plugin.macros[name]["enabled"]}, status=201)

    async def _api_update_macro(self, name: str, body: bytes) -> bytes:
        if name not in self.plugin.macros:
            return self._json_err(404, "宏不存在")
        data = self._read_body(body)
        if "commands" in data:
            cmds = data["commands"]
            if isinstance(cmds, list):
                self.plugin.macros[name]["commands"] = [str(c) for c in cmds]
        if "enabled" in data:
            self.plugin.macros[name]["enabled"] = bool(data["enabled"])
        if "name" in data:
            new_name = str(data["name"]).strip()
            if new_name and new_name != name:
                self.plugin.macros[new_name] = self.plugin.macros.pop(name)
                name = new_name
        self._save_macros()
        return self._json(self.plugin.macros.get(name, {}))

    def _api_del_macro(self, name: str) -> bytes:
        if name in self.plugin.macros:
            del self.plugin.macros[name]
            self._save_macros()
            self.plugin._audit_web("macro_del", f"name={name}")
        return self._json({"ok": True})

    # ==================== 脚本 API ====================

    def _api_scripts(self) -> bytes:
        sd = getattr(self.plugin, 'scripts_dir', None)
        if not sd or not os.path.isdir(sd):
            return self._json({"dir": str(sd), "files": []})
        files = []
        ss = getattr(self.plugin, 'script_settings', {})
        for fname in sorted(os.listdir(sd)):
            fp = os.path.join(sd, fname)
            if os.path.isfile(fp):
                sz = os.path.getsize(fp)
                preview = ""
                try:
                    with open(fp, 'r', encoding='utf-8') as f:
                        preview = f.read(4096)
                except Exception:
                    preview = "[binary]"
                fcfg = ss.get(fname, {})
                files.append({
                    "name": fname, "size": sz, "preview": preview,
                    "enabled": fcfg.get("enabled", True),
                })
        return self._json({"dir": sd, "files": files})

    async def _api_add_script(self, body: bytes) -> bytes:
        data = self._read_body(body)
        name = str(data.get("name", "")).strip()
        content = str(data.get("content", ""))
        if not name:
            return self._json_err(400, "missing name")
        sd = getattr(self.plugin, 'scripts_dir', None)
        if not sd or not os.path.isdir(sd):
            return self._json_err(500, "scripts_dir not found")
        fp = os.path.join(sd, name)
        with open(fp, 'w', encoding='utf-8') as f:
            f.write(content)
        return self._json({"name": name, "saved": True}, status=201)

    def _api_del_script(self, name: str) -> bytes:
        sd = getattr(self.plugin, 'scripts_dir', None)
        if not sd:
            return self._json_err(500, "scripts_dir not found")
        fp = os.path.join(sd, name)
        if os.path.isfile(fp):
            os.remove(fp)
        return self._json({"ok": True})

    async def _api_toggle_script(self, name: str, body: bytes) -> bytes:
        data = self._read_body(body)
        enabled = data.get("enabled", True)
        ss = getattr(self.plugin, 'script_settings', {})
        ss[name] = {"enabled": bool(enabled)}
        self.plugin.script_settings = ss
        self.plugin._save_script_settings()
        return self._json({"name": name, "enabled": bool(enabled)})

    def _api_custom_cmds(self, params=None) -> bytes:
        """列出某群的自定义命令"""
        gid = (params or {}).get("gid", [""])[0]
        if not gid:
            return self._json_err(400, "missing gid")
        cmds = self.plugin.custom_cmds.get(gid, [])
        return self._json(cmds)

    async def _api_add_custom_cmd(self, body: bytes) -> bytes:
        """添加自定义命令"""
        data = self._read_body(body)
        gid = str(data.get("gid", "")).strip()
        alias = str(data.get("alias", "")).strip()
        rcon_cmd = str(data.get("rcon_cmd", "")).strip()
        if not gid or not alias or not rcon_cmd:
            return self._json_err(400, "missing gid/alias/rcon_cmd")
        cmds = self.plugin.custom_cmds.setdefault(gid, [])
        now = int(time.time())
        item = {
            "alias": alias,
            "rcon_cmd": rcon_cmd,
            "description": str(data.get("description", "")).strip(),
            "enabled": data.get("enabled", True),
            "whitelist": [str(w).strip() for w in (data.get("whitelist", []) or []) if str(w).strip()],
            "show_reply": data.get("show_reply", True),
            "created_at": now,
        }
        cmds.append(item)
        self.plugin._save_custom_cmds()
        return self._json({"ok": True, "index": len(cmds) - 1})

    async def _api_update_custom_cmd(self, gid: str, idx: int, body: bytes) -> bytes:
        """更新自定义命令"""
        cmds = self.plugin.custom_cmds.get(gid, [])
        if idx < 0 or idx >= len(cmds):
            return self._json_err(404, "index out of range")
        data = self._read_body(body)
        item = cmds[idx]
        for k in ("alias", "rcon_cmd", "description", "enabled", "whitelist", "show_reply"):
            if k in data:
                if k == "whitelist":
                    item[k] = [str(w).strip() for w in (data.get(k, []) or []) if str(w).strip()]
                else:
                    item[k] = data[k]
        self.plugin._save_custom_cmds()
        return self._json({"ok": True})

    def _api_del_custom_cmd(self, gid: str, idx: int) -> bytes:
        """删除自定义命令"""
        cmds = self.plugin.custom_cmds.get(gid, [])
        if idx < 0 or idx >= len(cmds):
            return self._json_err(404, "index out of range")
        cmds.pop(idx)
        self.plugin._save_custom_cmds()
        return self._json({"ok": True})

    # ==================== 事件宏 API ====================

    @staticmethod
    def _normalize_commands(cmds) -> list:
        """规范化 commands：统一为 [{cmd, delay}] 格式"""
        if not isinstance(cmds, list):
            return []
        result = []
        for c in cmds:
            if isinstance(c, dict):
                result.append({
                    "cmd": str(c.get("cmd", "")),
                    "delay": float(c.get("delay", 0) or 0),
                })
            elif isinstance(c, str) and c.strip():
                result.append({"cmd": c.strip(), "delay": 0})
        return result

    @staticmethod
    def _normalize_event_types(data: dict) -> list:
        """规范化 event_types：支持新格式 [{type,pre_delay,post_delay,commands}] 和旧格式 ["string"]"""
        raw = data.get("event_types")
        if not raw:
            # 兼容旧的 event_type 单值字段
            evt = data.get("event_type", "")
            return [{"type": str(evt), "pre_delay": 0, "post_delay": 0, "commands": []}] if evt else []
        if not isinstance(raw, list):
            return []
        result = []
        for et in raw:
            if isinstance(et, dict):
                result.append({
                    "type": str(et.get("type", "")).strip(),
                    "pre_delay": float(et.get("pre_delay", 0) or 0),
                    "post_delay": float(et.get("post_delay", 0) or 0),
                    "commands": WebServer._normalize_commands(et.get("commands", [])),
                    "duration_minutes": int(et.get("duration_minutes", 0) or 0),
                    "duration_mode": str(et.get("duration_mode", "session") or "session"),
                    "duration_window_hours": int(et.get("duration_window_hours", 24) or 24),
                })
            elif isinstance(et, str) and et.strip():
                result.append({"type": et.strip(), "pre_delay": 0, "post_delay": 0, "commands": []})
        return result

    def _api_event_macros(self) -> bytes:
        """获取所有事件宏"""
        return self._json(self.plugin._event_macros)

    async def _api_event_macro_save(self, body: bytes, idx: int | None = None) -> bytes:
        """保存/更新事件宏"""
        data = self._read_body(body)
        macros = self.plugin._event_macros
        macro = {
            "id": str(int(time.time() * 1000)),
            "name": str(data.get("name", "")).strip(),
            "enabled": bool(data.get("enabled", False)),
            "event_type": str(data.get("event_type", "player_death")),
            "event_types": self._normalize_event_types(data),
            "server_name": str(data.get("server_name", "")).strip(),
            "commands": data.get("commands", []) if isinstance(data.get("commands"), list) else [str(data.get("commands", ""))],
            "cooldown": float(data.get("cooldown", 0) or 0),
            "player_name": str(data.get("player_name", "") or "").strip(),
            "event_param": str(data.get("event_param", "") or "").strip(),
            "max_triggers": int(data.get("max_triggers", 0) or 0),
            "trigger_window": int(data.get("trigger_window", 0) or 0),
            "qq_message": str(data.get("qq_message", "") or "").strip(),
            "gate_mode": str(data.get("gate_mode", "and") or "and"),
            "conditions": data.get("conditions", []) if isinstance(data.get("conditions"), list) else [],
        }
        if idx is not None and 0 <= idx < len(macros):
            # 检测是否为部分更新（仅 enable/disable toggle）
            if set(data.keys()) == {"enabled"}:
                macros[idx]["enabled"] = bool(data["enabled"])
                macro = macros[idx]
            else:
                macro["id"] = macros[idx].get("id", macro["id"])
                macros[idx] = macro
        else:
            macros.append(macro)
        cfg = self.plugin.config.setdefault("general", {})
        cfg["log_event_macros"] = macros
        self._save_config()
        self.plugin._save_event_macros_json()
        return self._json(macro, status=201 if idx is None else 200)

    def _api_event_macro_delete(self, idx: int) -> bytes:
        """删除事件宏"""
        macros = self.plugin._event_macros
        if idx < 0 or idx >= len(macros):
            return self._json_err(404, "index out of range")
        macros.pop(idx)
        cfg = self.plugin.config.setdefault("general", {})
        cfg["log_event_macros"] = macros
        self._save_config()
        self.plugin._save_event_macros_json()
        return self._json({"ok": True})

    def _api_event_macros_export(self) -> bytes:
        """导出事件宏 JSON"""
        import json
        return json.dumps(self.plugin._event_macros, ensure_ascii=False, indent=2).encode("utf-8")

    async def _api_event_macros_import(self, body: bytes) -> bytes:
        """导入事件宏 JSON（合并到现有列表）"""
        import json
        try:
            data = json.loads(body.decode("utf-8"))
            if not isinstance(data, list):
                return self._json_err(400, "JSON 必须是事件宏数组")
            imported = 0
            existing_ids = {m.get("id") for m in self.plugin._event_macros}
            for item in data:
                if not isinstance(item, dict):
                    continue
                if item.get("id") and item["id"] in existing_ids:
                    continue  # 跳过已存在的
                self.plugin._event_macros.append(item)
                imported += 1
            cfg = self.plugin.config.setdefault("general", {})
            cfg["log_event_macros"] = self.plugin._event_macros
            self._save_config()
            self.plugin._save_event_macros_json()
            return self._json({"ok": True, "imported": imported})
        except json.JSONDecodeError as e:
            return self._json_err(400, f"JSON 解析错误: {e}")


    # ==================== 日志查看器 API ====================

    def _api_log_viewer_recent(self, params: dict) -> bytes:
        """获取最近的日志条目"""
        limit = min(int((params or {}).get("limit", ["200"])[0]), 500)
        types_raw = (params or {}).get("types", [""])[0]
        types = [t for t in types_raw.split(",") if t] if types_raw else None
        server = (params or {}).get("server", [""])[0] or None
        player = (params or {}).get("player", [""])[0] or None
        entries = self.plugin._log_listener.get_recent(limit=limit, types=types, server=server, player=player)
        return self._json(entries)

    def _api_log_viewer_servers(self) -> bytes:
        """返回所有开启 web 管理的服务器（含日志配置）"""
        servers = []
        seen = set()
        for srvs in self.plugin.group_servers.values():
            for s in srvs:
                if s.get("web_management_enabled", True) is False:
                    continue
                sn = str(s.get("server_name", s.get("name", "")) or "")
                if not sn or sn in seen:
                    continue
                seen.add(sn)
                servers.append({
                    "name": sn,
                    "log_path": str(s.get("log_path", "") or ""),
                    "log_mode": str(s.get("log_mode", "") or ""),
                    "log_paths": s.get("log_paths", []) or [],
                    "log_folder": str(s.get("log_folder", "") or ""),
                    "log_file_pattern": str(s.get("log_file_pattern", "latest.log") or "latest.log"),
                })
        return self._json(servers)

    async def _api_log_viewer_set_log_path(self, body: bytes) -> bytes:
        """保存服务器的日志路径配置（支持文件/文件夹双模式）"""
        data = self._read_body(body)
        server_name = str(data.get("server_name", "")).strip()
        if not server_name:
            return self._json_err(400, "缺少 server_name")
        log_mode = str(data.get("log_mode", "file")).strip()
        found = 0
        for gid, srvs in self.plugin.group_servers.items():
            if not isinstance(srvs, list):
                continue
            for srv in srvs:
                sn = str(srv.get("server_name", srv.get("name", "")) or "")
                if sn == server_name:
                    srv["log_mode"] = log_mode
                    if log_mode == "file":
                        log_paths = data.get("log_paths", [])
                        if isinstance(log_paths, str):
                            log_paths = [p.strip() for p in log_paths.replace("\n", ",").split(",") if p.strip()]
                        srv["log_paths"] = log_paths
                        srv["log_path"] = ""  # 清除旧格式
                    elif log_mode == "folder":
                        srv["log_folder"] = str(data.get("log_folder", "") or "").strip()
                        srv["log_file_pattern"] = str(data.get("log_file_pattern", "latest.log") or "latest.log").strip()
                        srv["log_paths"] = []
                        srv["log_path"] = ""  # 清除旧格式
                    found += 1
        if found:
            self.plugin._save_server_log_configs()
            self.plugin.config.save_config()
            self.plugin._audit_web("log_path", f"server={server_name} mode={log_mode}")
            return self._json({"ok": True, "updated": found})
        return self._json_err(404, f"未找到服务器: {server_name}")

    def _api_log_viewer_test(self, params: dict) -> bytes:
        """检测日志文件可读性：读取服务器日志最后 100 行并返回诊断信息"""
        import os as _os
        server = (params or {}).get("server", [""])[0] or None
        if not server:
            return self._json_err(400, "请选择服务器")
        # 查找服务器日志路径
        log_paths = []
        for srvs in self.plugin.group_servers.values():
            for s in srvs:
                sn = str(s.get("server_name", s.get("name", "")) or "")
                if sn != server:
                    continue
                log_mode = str(s.get("log_mode", "") or "").strip()
                if not log_mode:
                    lp = str(s.get("log_path", "") or "").strip()
                    if lp:
                        log_paths.append(lp)
                elif log_mode == "file":
                    lps = s.get("log_paths", [])
                    if isinstance(lps, str):
                        lps = [p.strip() for p in lps.split(",") if p.strip()]
                    for lp in lps:
                        lp = str(lp).strip()
                        if lp:
                            log_paths.append(lp)
                elif log_mode == "folder":
                    folder = str(s.get("log_folder", "") or "").strip()
                    pattern = str(s.get("log_file_pattern", "latest.log") or "latest.log").strip()
                    if folder:
                        log_paths.append(_os.path.join(folder, pattern).replace("\\", "/"))
                break
        if not log_paths:
            return self._json({
                "ok": False,
                "error": "未配置日志路径",
                "hint": "请在服务器管理中为此服务器填写日志文件路径"
            })
        results = []
        for lp in log_paths:
            r = {"path": lp, "exists": False, "readable": False, "size": 0, "lines": 0, "sample": []}
            if not _os.path.exists(lp):
                r["error"] = "文件不存在"
                results.append(r)
                continue
            r["exists"] = True
            try:
                r["size"] = _os.path.getsize(lp)
            except Exception:
                r["error"] = "无法获取文件大小"
                results.append(r)
                continue
            try:
                with open(lp, "r", encoding="utf-8", errors="ignore") as f:
                    # 读取最后 ~8KB 再截取最后 100 行
                    f.seek(0, 2)
                    fsize = f.tell()
                    chunk = max(0, fsize - 8192)
                    f.seek(chunk)
                    lines = f.read().splitlines()
                    # 截取最后 100 行
                    last_lines = lines[-100:] if len(lines) > 100 else lines
                    r["lines"] = len(last_lines)
                    r["readable"] = True
                    # 只返回前 5 行和后 5 行作为样本
                    if len(last_lines) <= 10:
                        r["sample"] = last_lines
                    else:
                        r["sample"] = last_lines[:5] + ["..."] + last_lines[-5:]
            except Exception as e:
                r["error"] = str(e)
            results.append(r)
        total_readable = sum(1 for r in results if r.get("readable"))
        total_lines = sum(r.get("lines", 0) for r in results)
        return self._json({
            "ok": total_readable > 0,
            "server": server,
            "paths": results,
            "summary": f"共 {len(results)} 个路径，{total_readable} 个可读，共 {total_lines} 行样本" if results else "无路径"
        })

    def _api_quick_cmd_settings(self) -> bytes:
        ss = getattr(self.plugin, 'quick_cmd_settings', {})
        return self._json(ss)

    async def _api_toggle_quick_cmd(self, name: str, body: bytes) -> bytes:
        data = self._read_body(body)
        enabled = data.get("enabled", True)
        ss = getattr(self.plugin, 'quick_cmd_settings', {})
        ss[name] = {"enabled": bool(enabled)}
        self.plugin.quick_cmd_settings = ss
        self.plugin._save_quick_cmd_settings()
        return self._json({"name": name, "enabled": bool(enabled)})

    def _api_quick_cmds_config(self) -> bytes:
        import json as _json
        path = os.path.join(self.plugin.plugin_data_dir, "quick_cmds.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return self._json(_json.load(f))
            except Exception:
                pass
        return self._json({})

    def _api_save_quick_cmds_config(self, body: bytes) -> bytes:
        import json as _json
        data = self._read_body(body)
        path = os.path.join(self.plugin.plugin_data_dir, "quick_cmds.json")
        with open(path, "w", encoding="utf-8") as f:
            _json.dump(data, f, ensure_ascii=False, indent=2)
        return self._json({"ok": True})

    # ==================== 持久化 ====================

    def _save_config(self):
        try:
            servers_list = []
            bound_gids = set()
            for gid, srvs in self.plugin.group_servers.items():
                bound_gids.add(str(gid))
                for s in srvs:
                    sc = {k: v for k, v in s.items()}
                    sc["group_id"] = gid
                    servers_list.append(sc)
            self.plugin.config["servers"] = servers_list
            # 同步 groups 列表：保留用户配置的群号 + 已绑定的群号
            existing = set(str(g).strip() for g in (self.plugin.config.get("groups", []) or []))
            self.plugin.config["groups"] = sorted(existing | bound_gids)
            self.plugin.config.save_config()
            # 同时持久化服务器日志配置到独立 JSON 文件
            self.plugin._save_server_log_configs()
        except Exception as e:
            logger.error(f"[mrcon] Web 保存配置失败: {e}")

    def _save_macros(self):
        try:
            macros_list = []
            for name, data in self.plugin.macros.items():
                macros_list.append({
                    "name": name,
                    "commands": data.get("commands", []),
                    "enabled": data.get("enabled", True),
                })
            self.plugin.config["macro_definitions"] = macros_list
            self.plugin.config.save_config()
        except Exception as e:
            logger.error(f"[mrcon] Web 保存宏失败: {e}")

    # ==================== 服务器配置模板 CRUD ====================

    def _save_templates(self):
        try:
            tp = os.path.join(self.plugin.plugin_data_dir, "server_templates.json")
            os.makedirs(os.path.dirname(tp), exist_ok=True)
            with open(tp, "w", encoding="utf-8") as f:
                json.dump(self.plugin.server_templates, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[mrcon] 保存服务器模板失败: {e}")

    def _api_list_templates(self) -> bytes:
        return self._json(self.plugin.server_templates)

    async def _api_add_template(self, body: bytes) -> bytes:
        data = self._read_body(body)
        name = str(data.get("name", "")).strip()
        if not name:
            return self._json_err(400, "missing name")
        for t in self.plugin.server_templates:
            if t.get("name") == name:
                return self._json_err(409, "模板名称已存在")
        tpl = {
            "name": name,
            "rcon_host": str(data.get("rcon_host", "")),
            "rcon_port": str(data.get("rcon_port", "25575")),
            "rcon_password": str(data.get("rcon_password", "")),
            "game_port": str(data.get("game_port", "25565")),
            "query_enabled": bool(data.get("query_enabled", True)),
        }
        self.plugin.server_templates.append(tpl)
        self._save_templates()
        return self._json(tpl, status=201)

    async def _api_update_template(self, name: str, body: bytes) -> bytes:
        data = self._read_body(body)
        for t in self.plugin.server_templates:
            if t.get("name") == name:
                if "rcon_host" in data:
                    t["rcon_host"] = str(data["rcon_host"])
                if "rcon_port" in data:
                    t["rcon_port"] = str(data["rcon_port"])
                if "rcon_password" in data:
                    t["rcon_password"] = str(data["rcon_password"])
                if "game_port" in data:
                    t["game_port"] = str(data["game_port"])
                if "query_enabled" in data:
                    t["query_enabled"] = bool(data["query_enabled"])
                new_name = str(data.get("name", "")).strip()
                if new_name and new_name != name:
                    t["name"] = new_name
                self._save_templates()
                return self._json(t)
        return self._json_err(404, "模板不存在")

    def _api_delete_template(self, name: str) -> bytes:
        for i, t in enumerate(self.plugin.server_templates):
            if t.get("name") == name:
                self.plugin.server_templates.pop(i)
                self._save_templates()
                return self._json({"ok": True})
        return self._json_err(404, "模板不存在")

    # ==================== 群名称 API ====================

    def _api_list_group_names(self) -> bytes:
        return self._json(self.plugin.group_names)

    async def _api_set_group_name(self, gid: str, body: bytes) -> bytes:
        data = self._read_body(body)
        name = str(data.get("name", "")).strip()
        if not name:
            return self._json_err(400, "missing name")
        self.plugin.group_names[str(gid)] = name
        # 同步回 config
        self.plugin.config["group_names"] = dict(self.plugin.group_names)
        try:
            self.plugin.config.save_config()
        except Exception as e:
            logger.error(f"[mrcon] 保存群名称失败: {e}")
        return self._json({"gid": str(gid), "name": name})

    def _api_delete_group_name(self, gid: str) -> bytes:
        self.plugin.group_names.pop(str(gid), None)
        self.plugin.config["group_names"] = dict(self.plugin.group_names)
        self.plugin.config.save_config()
        return self._json({"ok": True})

    # ==================== 参数化命令模板 CRUD ====================

    def _save_cmd_tpls(self):
        try:
            tp = os.path.join(self.plugin.plugin_data_dir, "cmd_templates.json")
            os.makedirs(os.path.dirname(tp), exist_ok=True)
            with open(tp, "w", encoding="utf-8") as f:
                json.dump(self.plugin.cmd_templates, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[mrcon] 保存命令模板失败: {e}")

    def _api_list_cmd_tpls(self) -> bytes:
        return self._json(self.plugin.cmd_templates)

    async def _api_add_cmd_tpl(self, body: bytes) -> bytes:
        data = self._read_body(body)
        name = str(data.get("name", "")).strip()
        if not name:
            return self._json_err(400, "missing name")
        for t in self.plugin.cmd_templates:
            if t.get("name") == name:
                return self._json_err(409, "模板名称已存在")
        tpl = {
            "name": name,
            "desc": str(data.get("desc", "")),
            "enabled": bool(data.get("enabled", True)),
            "commands": data.get("commands", []) if isinstance(data.get("commands"), list) else [],
            "params": data.get("params", []) if isinstance(data.get("params"), list) else [],
        }
        self.plugin.cmd_templates.append(tpl)
        self._save_cmd_tpls()
        return self._json(tpl, status=201)

    async def _api_update_cmd_tpl(self, name: str, body: bytes) -> bytes:
        data = self._read_body(body)
        for t in self.plugin.cmd_templates:
            if t.get("name") == name:
                if "desc" in data:
                    t["desc"] = str(data["desc"])
                if "enabled" in data:
                    t["enabled"] = bool(data["enabled"])
                if "commands" in data and isinstance(data["commands"], list):
                    t["commands"] = data["commands"]
                if "params" in data and isinstance(data["params"], list):
                    t["params"] = data["params"]
                new_name = str(data.get("name", "")).strip()
                if new_name and new_name != name:
                    t["name"] = new_name
                self._save_cmd_tpls()
                return self._json(t)
        return self._json_err(404, "模板不存在")

    def _api_delete_cmd_tpl(self, name: str) -> bytes:
        for i, t in enumerate(self.plugin.cmd_templates):
            if t.get("name") == name:
                self.plugin.cmd_templates.pop(i)
                self._save_cmd_tpls()
                return self._json({"ok": True})
        return self._json_err(404, "模板不存在")

    # ==================== 上线触发器 CRUD ====================

    def _api_list_ot(self) -> bytes:
        return self._json(self.plugin.online_triggers)

    async def _api_add_ot(self, body: bytes) -> bytes:
        data = self._read_body(body)
        name = str(data.get("name", "")).strip()
        if not name:
            return self._json_err(400, "missing name")
        for t in self.plugin.online_triggers:
            if t.get("name") == name:
                return self._json_err(409, "触发器名称已存在")
        tpl = {
            "name": name,
            "enabled": bool(data.get("enabled", True)),
            "player": str(data.get("player", "")).strip(),
            "match_type": str(data.get("match_type", "exact")),
            "commands": data.get("commands", []) if isinstance(data.get("commands"), list) else [],
            "cooldown_seconds": int(data.get("cooldown_seconds", 300)),
            "note": str(data.get("note", "")),
        }
        self.plugin.online_triggers.append(tpl)
        self.plugin._save_online_triggers()
        return self._json(tpl, status=201)

    async def _api_update_ot(self, name: str, body: bytes) -> bytes:
        data = self._read_body(body)
        for t in self.plugin.online_triggers:
            if t.get("name") == name:
                if "enabled" in data:
                    t["enabled"] = bool(data["enabled"])
                if "player" in data:
                    t["player"] = str(data.get("player", "")).strip()
                if "match_type" in data:
                    t["match_type"] = str(data["match_type"])
                if "commands" in data and isinstance(data["commands"], list):
                    t["commands"] = data["commands"]
                if "cooldown_seconds" in data:
                    t["cooldown_seconds"] = int(data["cooldown_seconds"])
                if "note" in data:
                    t["note"] = str(data["note"])
                new_name = str(data.get("name", "")).strip()
                if new_name and new_name != name:
                    t["name"] = new_name
                self.plugin._save_online_triggers()
                return self._json(t)
        return self._json_err(404, "触发器不存在")

    def _api_delete_ot(self, name: str) -> bytes:
        for i, t in enumerate(self.plugin.online_triggers):
            if t.get("name") == name:
                self.plugin.online_triggers.pop(i)
                self.plugin._save_online_triggers()
                return self._json({"ok": True})
        return self._json_err(404, "触发器不存在")