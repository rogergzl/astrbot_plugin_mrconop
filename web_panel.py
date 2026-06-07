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
from pathlib import Path
from html import escape
from typing import Dict, List, Optional, Set, Tuple, Any
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

from astrbot.api import logger

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
.ma main{flex:1;padding:24px;overflow-y:auto;max-width:1500px}
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
.oh-bar:hover{opacity:.8}
.oh-tip{display:none;position:absolute;top:-56px;left:50%;transform:translateX(-50%);background:#333;color:#fff;padding:6px 10px;border-radius:5px;font-size:11px;white-space:nowrap;z-index:99;pointer-events:none;line-height:1.6;box-shadow:0 2px 8px rgba(0,0,0,.3)}
.oh-bar:hover .oh-tip{display:block;z-index:9999}
.oh-chart .oh-bar:first-child .oh-tip{left:0;transform:none}
.oh-chart .oh-bar:last-child .oh-tip{left:auto;right:0;transform:none}
/* Settings form */
.sf{max-width:1100px}
.sg{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}
.sg-item{background:var(--bg);border:1px solid var(--b);border-radius:6px;padding:12px}
.sg-item h4{margin:0 0 10px;font-size:13px;color:var(--w);padding-bottom:8px;border-bottom:1px solid var(--b)}
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
  <h2>MRCon<span class="ver">v3.20.0</span></h2>
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
function toast(m,e){var t=d.getElementById("toast");t.className="toast "+(e?"te":"to");t.textContent=m;t.style.display="block";setTimeout(function(){t.style.display="none"},2500)}
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
    }catch(e){login("密码错误",true)}
    return false
}
async function dologout(){await fetch(A+"/logout",{method:"POST"});login()}
async function chk(){
    try{
        var r=await fetch(A+"/auth");
        if(r.ok){panel()}else{login()}
    }catch(e){login()}
}
function panel(){
    d.getElementById("login-root").style.display="none";
    d.getElementById("sb").style.display="flex";
    d.getElementById("ma").style.display="flex";
    load(tab||"dashboard")
}
function nav(t){tab=t;document.getElementById("pt").textContent=document.querySelector('[data-tab="'+t+'"]').textContent.trim();document.querySelectorAll(".sb nav a").forEach(function(a){a.classList.toggle("on",a.dataset.tab===t)});if(rf){clearInterval(rf);rf=null}load(t)}
function refresh(ms,cb){if(rf)clearInterval(rf);if(ms>0)rf=setInterval(cb,ms)}
function load(t){var m={dashboard:loD,servers:loS,relay:loRe,tracker:loTr,players:loP,compensations:loCm,exchange:loEx,lottery:loLo,online:loOn,audit:loAu,macros:loMa,scripts:loSc,cmd:loCmd,settings:loCfg};if(m[t])m[t]()}
/* ====== 仪表盘 ====== */
async function loD(){var s=await fj(A+"/status"),pc=await fj(A+"/compensations/count?status=pending");document.getElementById("main").innerHTML='<div class="sts"><div class="st" onclick="nav(\'servers\')"><div class="n">'+(s.group_count||0)+'</div><div class="l">群聊数量</div></div><div class="st" onclick="nav(\'servers\')"><div class="n">'+(s.server_count||0)+'</div><div class="l">服务器数量</div></div><div class="st" onclick="nav(\'players\')"><div class="n">'+(s.player_count||0)+'</div><div class="l">玩家总数</div></div><div class="st" onclick="nav(\'online\')"><div class="n">'+(s.online_count||0)+'</div><div class="l">当前在线</div></div><div class="st" onclick="nav(\'compensations\')"><div class="n">'+(pc.count||0)+'</div><div class="l">待处理补偿</div></div><div class="st" onclick="nav(\'settings\')"><div class="n">'+(s.admin_count||0)+'</div><div class="l">管理员</div></div><div class="st" onclick="nav(\'macros\')"><div class="n">'+(s.macro_count||0)+'</div><div class="l">宏命令</div></div><div class="st" onclick="nav(\'scripts\')"><div class="n">'+(s.script_count||0)+'</div><div class="l">脚本文件</div></div></div><div class="ct"><h3>全局状态</h3><table><tr><th>功能模块</th><th>运行状态</th><th>关键参数</th></tr><tr><td>群服互联</td><td><span class="t1 '+(s.relay_enabled?'t-on':'t-off')+'">'+(s.relay_enabled?'已开启':'已关闭')+'</span></td><td>'+s.relay_fmt+'</td></tr><tr><td>在线追踪</td><td><span class="t1 '+(s.tracker_enabled?'t-on':'t-off')+'">'+(s.tracker_enabled?'已开启':'已关闭')+'</span></td><td>轮询间隔 '+s.tracker_interval+'秒 / 踢出阈值 '+s.kick_threshold+'分钟</td></tr><tr><td>玩家数据库</td><td><span class="t1 '+(s.pdb_enabled?'t-on':'t-off')+'">'+(s.pdb_enabled?'已开启':'已关闭')+'</span></td><td>签到积分 '+s.checkin_pts+' / 补偿功能 '+(s.comp_enabled?'开启':'关闭')+'</td></tr><tr><td>速率限制</td><td><span class="t1 '+(s.rate_enabled?'t-on':'t-off')+'">'+(s.rate_enabled?'已开启':'已关闭')+'</span></td><td>基础 '+s.rate_base+'ms / 阈值 '+s.rate_threshold+'次</td></tr><tr><td>危险命令黑名单</td><td><span class="t1 '+(s.dangerous_count>0?'t-off':'t-on')+'">'+(s.dangerous_count>0?'已启用('+s.dangerous_count+'条)':'未设置')+'</span></td><td style="font-size:11px;color:var(--m)">'+(s.dangerous_list||[]).join(', ')||'-'+'</td></tr></table></div>'}
/* ====== Servers ====== */
async function loS(){var g=await fj(A+"/groups"),gns=await fj(A+"/group-names"),h='<div class="fb"><h3 style="margin:0">服务器管理</h3><button class="b1 bs" onclick="addSvr()">+ 添加</button><button class="b2 bsm" style="margin-left:8px" onclick="loTpls()">📋 模板管理</button></div>';for(var id in g){var s=g[id]||[],nm=gns[id]||'';h+='<div class="ct"><h3>群 '+id+(nm?' ('+nm+')':'')+'<span class="badge">'+s.length+'台</span><button class="b2 bsm" onclick="addSvrG(\''+id+'\')">+ 添加</button></h3>';s.forEach(function(sv,i){h+='<div style="background:var(--bg);border-radius:4px;padding:10px;margin-bottom:5px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px"><div><strong>'+(sv.server_name||sv.name||'未命名')+'</strong><span style="color:var(--m);margin-left:6px;font-size:10px">'+sv.rcon_host+':'+sv.rcon_port+'</span><span class="t1 '+(sv.relay_enabled?'t-on':'t-off')+'" title="群服互联">互联</span><span class="t1 '+(sv.query_enabled!==false?'t-on':'t-off')+'">query</span><span class="t1 '+(sv.web_management_enabled!==false?'t-on':'t-off')+'">web</span>'+(sv.vote_enabled?'<span class="t1 t-on">vote:'+sv.vote_threshold+'</span>':'')+'</div><div class="ac"><button class="b2 bsm" onclick="edSvr(\''+id+'\','+i+')">编辑</button><button class="bd bsm" onclick="rmSvr(\''+id+'\','+i+')">删除</button></div></div>'});h+='</div>'}if(!Object.keys(g).length)h+='<div class="emp">暂无群聊</div>';document.getElementById("main").innerHTML=h}
function addSvr(){svrModal()}
function addSvrG(gid){svrModal(gid)}
function svrModal(gid){var m='<div class="mbg" id="sv-m" onclick="if(event.target===this)this.remove()"><div class="mod"><h3>'+(gid?'添加服务器到群 '+gid:'添加服务器')+'</h3>';if(!gid){m+='<div class="fr"><div class="fg"><label>📋 从模板填充</label><select id="stpl" onchange="fillTpl(\'stpl\',\'sf\')"><option value="">-- 手动填写 --</option></select></div><div class="fg"><label>📋 从已有群聊选择</label><select id="stpl-grp" onchange="svrSelGrp(this.value)"><option value="">-- 选择群聊 --</option></select></div></div>'}m+='<div class="fg"><label title="QQ群号">群号 *</label><input id="sfg" value="'+(gid||'')+'" '+(gid?'readonly':'')+'></div>';if(gid){m+='<div class="fg"><label title="从模板填充">📋 从模板填充</label><select id="stpl" onchange="fillTpl(\'stpl\',\'sf\')"><option value="">-- 手动填写 --</option></select></div>'}m+='<div class="fr"><div class="fg"><label title="服务器显示名称">名称 *</label><input id="sfn" placeholder="生存一区"></div><div class="fg"><label title="RCON服务器地址">RCON地址 *</label><input id="sfh" placeholder="127.0.0.1"></div></div><div class="fr"><div class="fg"><label title="RCON端口号">RCON端口 *</label><input id="sfp" value="25575"></div><div class="fg"><label title="RCON连接密码">密码 *</label><input id="sfpw" type="password"></div><div class="fg"><label title="MC游戏端口">游戏端口</label><input id="sfgp" value="25565"></div></div><div class="fg"><label title="允许使用命令的QQ号，逗号分隔">白名单</label><input id="sfw" placeholder="111,222"></div><div class="fg"><label title="公开可用的命令列表，逗号分隔">公开命令</label><input id="sfu" value="list,say"></div><div class="fr"><div class="fg"><label title="群服互联开关">群服互联</label><select id="sfrl"><option value="0">关</option><option value="1">开</option></select></div><div class="fg"><label title="允许查询此服务器状态">查询</label><select id="sfq"><option value="1">开</option><option value="0">关</option></select></div><div class="fg"><label title="允许此群在Web面板中管理">Web管理</label><select id="sfwm"><option value="1" selected>开</option><option value="0">关</option></select></div></div><div style="margin-top:10px;padding-top:10px;border-top:1px solid var(--b)"><h4 style="font-size:12px;color:var(--m);margin-bottom:8px">投票</h4><div class="fr"><div class="fg"><label title="允许群内发起投票">开关</label><select id="sfvt0"><option value="0">关</option><option value="1">开</option></select></div><div class="fg"><label title="投票所需赞同人数">阈值</label><input id="sfvt" value="3" type="number"></div><div class="fg"><label title="投票有效期(秒)">TTL</label><input id="sfvttl" value="60" type="number"></div></div><div class="fr"><div class="fg"><label title="超时最小赞同人数">最小赞同</label><input id="sfvma" value="1" type="number"></div><div class="fg"><label title="平票处理策略">平票</label><select id="sfvts"><option value="fail">失败</option><option value="admin">裁决</option></select></div><div class="fg"><label title="管理员裁决超时(秒)">裁决TTL</label><input id="sfatl" value="120" type="number"></div></div></div><div class="fr" style="margin-top:14px"><button class="b1 bs" onclick="doAddSvr()">保存</button><button class="b2 bs" onclick="document.getElementById(\'sv-m\').remove()">取消</button></div></div></div>';document.body.insertAdjacentHTML("beforeend",m);fj(A+"/server-templates").then(function(t){window._tpls=t;var s=document.getElementById("stpl");if(s){t.forEach(function(v){s.innerHTML+='<option value=\"'+v.name+'\">'+v.name+'</option>'})}});if(!gid){fj(A+"/config-servers").then(function(cs){var grps=cs&&cs.groups?cs.groups:[];var gns=cs&&cs.group_names?cs.group_names:{};var s=document.getElementById("stpl-grp");if(s){grps.forEach(function(g){var gn=gns[g]||'';s.innerHTML+='<option value=\"'+g+'\">'+(gn?g+' ('+gn+')':'群 '+g)+'</option>'})}})}}
async function doAddSvr(){var g=document.getElementById("sfg").value.trim();if(!g){toast("请输入群号",true);return}var b={group_id:g,name:document.getElementById("sfn").value.trim(),rcon_host:document.getElementById("sfh").value.trim(),rcon_port:document.getElementById("sfp").value.trim(),rcon_password:document.getElementById("sfpw").value.trim(),game_port:document.getElementById("sfgp").value.trim(),whitelist_qqs:document.getElementById("sfw").value.split(",").map(function(s){return s.trim()}).filter(Boolean),public_commands:document.getElementById("sfu").value.split(",").map(function(s){return s.trim()}).filter(Boolean),relay_enabled:document.getElementById("sfrl").value=="1",query_enabled:document.getElementById("sfq").value=="1",web_management_enabled:document.getElementById("sfwm").value=="1",vote_enabled:document.getElementById("sfvt0").value=="1",vote_threshold:parseInt(document.getElementById("sfvt").value)||3,vote_ttl:parseInt(document.getElementById("sfvttl").value)||60,vote_min_agree_on_timeout:parseInt(document.getElementById("sfvma").value)||1,vote_tie_strategy:document.getElementById("sfvts").value,admin_decide_ttl:parseInt(document.getElementById("sfatl").value)||120};await pj(A+"/servers",b);document.getElementById("sv-m")?.remove();toast("已添加");loS()}
async function edSvr(gid,idx){var s=await fj(A+"/servers/"+gid+"/"+idx);var m='<div class="mbg" id="es-m" onclick="if(event.target===this)this.remove()"><div class="mod"><h3>编辑: '+(s.server_name||s.name)+'</h3><div class="fg"><label title="从模板填充">📋 从模板填充</label><select id="etpl" onchange="fillTpl(\'etpl\',\'ef\')"><option value="">-- 手动填写 --</option></select></div><div class="fr"><div class="fg"><label title="服务器显示名称">名称</label><input id="efn" value="'+(s.server_name||s.name||'')+'" title="修改服务器在面板中的显示名称，不影响RCON连接"></div><div class="fg"><label title="RCON服务器地址">RCON地址</label><input id="efh" value="'+(s.rcon_host||'')+'" title="修改MC服务器的RCON地址，如 127.0.0.1 或公网IP"></div></div><div class="fr"><div class="fg"><label title="RCON端口号">端口</label><input id="efp" value="'+(s.rcon_port||'')+'" title="修改RCON端口，默认25575，需与server.properties中一致"></div><div class="fg"><label title="RCON连接密码">密码</label><input id="efpw" value="'+(s.rcon_password||'')+'" title="修改RCON连接密码，需与server.properties中rcon.password一致"></div><div class="fg"><label title="MC游戏端口">游戏端口</label><input id="efgp" value="'+(s.game_port||'25565')+'" title="MC服务器游戏端口，默认25565，用于状态查询"></div></div><div class="fg"><label title="允许使用命令的QQ号，逗号分隔">白名单</label><input id="efw" value="'+(s.whitelist_qqs||[]).join(',')+'" title="允许直接执行RCON命令的QQ号，逗号分隔"></div><div class="fg"><label title="公开可用的命令列表，逗号分隔">公开命令</label><input id="efu" value="'+(s.public_commands||[]).join(',')+'" title="非白名单用户可执行的命令，逗号分隔，如 list,say"></div><div class="fr"><div class="fg"><label title="群服互联开关">群服互联</label><select id="efrl"><option value="1" '+(s.relay_enabled?'selected':'')+'>开</option><option value="0" '+(!s.relay_enabled?'selected':'')+'>关</option></select></div><div class="fg"><label title="允许查询此服务器状态">查询</label><select id="efq"><option value="1" '+(s.query_enabled!==false?'selected':'')+'>开</option><option value="0" '+(s.query_enabled===false?'selected':'')+'>关</option></select></div><div class="fg"><label title="共享到其他群">共享</label><select id="efsh"><option value="0">否</option><option value="1" '+(s.shared?'selected':'')+'>是</option></select></div><div class="fg"><label title="允许此群在Web面板中管理">Web管理</label><select id="efwm"><option value="1" '+(s.web_management_enabled!==false?'selected':'')+'>开</option><option value="0" '+(s.web_management_enabled===false?'selected':'')+'>关</option></select></div></div><div style="margin-top:10px;padding-top:10px;border-top:1px solid var(--b)"><h4 style="font-size:12px;color:var(--m);margin-bottom:8px">投票</h4><div class="fr"><div class="fg"><label title="允许群内发起投票">开关</label><select id="efvt0"><option value="1" '+(s.vote_enabled?'selected':'')+'>开</option><option value="0" '+(!s.vote_enabled?'selected':'')+'>关</option></select></div><div class="fg"><label title="投票所需赞同人数">阈值</label><input id="efvt" value="'+(s.vote_threshold||3)+'" type="number" title="投票通过所需最少赞同人数"></div><div class="fg"><label title="投票有效期(秒)">TTL</label><input id="efvttl" value="'+(s.vote_ttl||60)+'" type="number" title="投票超时时间(秒)"></div></div><div class="fr"><div class="fg"><label title="超时最小赞同人数">最小赞同</label><input id="efvma" value="'+(s.vote_min_agree_on_timeout||1)+'" type="number" title="投票超时所需最小赞同人数"></div><div class="fg"><label title="平票处理策略">平票</label><select id="efvts"><option value="fail" '+(s.vote_tie_strategy==='fail'?'selected':'')+'>失败</option><option value="admin" '+(s.vote_tie_strategy==='admin'?'selected':'')+'>裁决</option></select></div><div class="fg"><label title="管理员裁决超时(秒)">裁决TTL</label><input id="efatl" value="'+(s.admin_decide_ttl||120)+'" type="number" title="平票时管理员裁决超时(秒)"></div></div></div><div class="fr" style="margin-top:14px"><button class="b1 bs" onclick="doEdSvr(\''+gid+'\','+idx+')">保存</button><button class="b2 bs" onclick="document.getElementById(\'es-m\').remove()">取消</button></div></div></div>';document.body.insertAdjacentHTML("beforeend",m);fj(A+"/server-templates").then(function(t){window._tpls=t;var s=document.getElementById("etpl");if(s){t.forEach(function(v){s.innerHTML+='<option value=\"'+v.name+'\">'+v.name+'</option>'})}})}
async function doEdSvr(gid,idx){var b={name:document.getElementById("efn").value.trim(),rcon_host:document.getElementById("efh").value.trim(),rcon_port:document.getElementById("efp").value.trim(),rcon_password:document.getElementById("efpw").value.trim(),game_port:document.getElementById("efgp").value.trim(),whitelist_qqs:document.getElementById("efw").value.split(",").map(function(s){return s.trim()}).filter(Boolean),public_commands:document.getElementById("efu").value.split(",").map(function(s){return s.trim()}).filter(Boolean),relay_enabled:document.getElementById("efrl").value=="1",query_enabled:document.getElementById("efq").value=="1",shared:document.getElementById("efsh").value=="1",web_management_enabled:document.getElementById("efwm").value=="1",vote_enabled:document.getElementById("efvt0").value=="1",vote_threshold:parseInt(document.getElementById("efvt").value)||3,vote_ttl:parseInt(document.getElementById("efvttl").value)||60,vote_min_agree_on_timeout:parseInt(document.getElementById("efvma").value)||1,vote_tie_strategy:document.getElementById("efvts").value,admin_decide_ttl:parseInt(document.getElementById("efatl").value)||120};await pjt(A+"/servers/"+gid+"/"+idx,b);document.getElementById("es-m")?.remove();toast("已更新");loS()}
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
async function loRe(){var g=await fj(A+"/groups?filter_web_mgmt=1"),all=await fj(A+"/relay/all"),gc=await fj(A+"/config/relay");window._gc=gc;var allSrv=[],seen={};for(var gid in g){var srvs=g[gid]||[];for(var i=0;i<srvs.length;i++){var s=srvs[i];var sn=s.server_name||s.name||'';if(sn&&!seen[sn]){seen[sn]=true;allSrv.push(sn)}}}var h='<div class="ct"><h3>全局互联设置</h3><table><tr><th>群→服</th><th>服→群</th><th>必须 /msay</th><th>群→服格式</th><th>服→群格式</th></tr><tr><td><label class="tg" title="全局群聊→服务器消息转发"><input type="checkbox" '+(gc.relay_group_to_mc?'checked':'')+' onchange="relayGlobalSet(\'relay_group_to_mc\',this.checked)"><span class="sl"></span></label></td><td><label class="tg" title="全局服务器→群聊消息转发"><input type="checkbox" '+(gc.relay_mc_to_group?'checked':'')+' onchange="relayGlobalSet(\'relay_mc_to_group\',this.checked)"><span class="sl"></span></label></td><td><label class="tg" title="必须 /msay 才允许转发"><input type="checkbox" '+(gc.relay_require_msay?'checked':'')+' onchange="relayGlobalSet(\'relay_require_msay\',this.checked)"><span class="sl"></span></label></td><td style="min-width:200px">'+fmtEditor('fmt_group',gc.relay_fmt_group||'[QQ] {name}: {msg}','','',true)+'</td><td style="min-width:200px">'+fmtEditor('fmt_mc',gc.relay_fmt_mc||'[MC] {player}: {msg}','','',true)+'</td></tr></table></div><div class="ct" style="margin:8px 0;background:rgba(255,193,7,.06);border:1px dashed rgba(255,193,7,.25);padding:8px 12px;border-radius:4px;font-size:11px;line-height:1.6"><span style="color:var(--m)">⚠ 服→群转发需 MC 服务端安装配套模组：</span><a href="https://github.com/rogergzl/astrbot_plugin_mrconop" target="_blank" style="color:var(--s);text-decoration:underline;margin-left:4px">📥 下载 MC 模组（待开发）</a><br><span style="color:var(--m);font-size:10px">当前服→群暂不可用，待模组发布后安装到 MC 服务器即可生效</span></div><div class="fb" style="margin:16px 0 8px"><h3 style="margin:0">群-服绑定</h3><button class="b1 bsm" onclick="relayAutoBind()">🔄 自动绑定所有</button></div>';var has=false;for(var gid in g){var entries=all[gid]||[],srvs=g[gid]||[],nm=gn(srvs),dnm=(nm?nm+' (':'')+'QQ:'+gid+(nm?')':'');if(!entries.length)entries=[{server_name:srvs[0]?.server_name||srvs[0]?.name||'',group_to_mc:false,mc_to_group:false,mode:'off'}];has=true;var mode=(entries[0]&&entries[0].mode)||'off';h+='<div class="rl-card"><span class="rl-grp">'+dnm+'</span><select style="width:100px;margin-right:8px" onchange="relaySetMode(\''+gid+'\',this.value)"><option value="off"'+(mode==='off'?' selected':'')+'>不互通</option><option value="global"'+(mode==='global'?' selected':'')+'>遵循全局</option><option value="custom"'+(mode==='custom'?' selected':'')+'>独立配置</option></select><button class="b1 bsm" style="font-size:11px" onclick="relayAddEntry(\''+gid+'\')" title="添加额外服务器绑定">+ 添加</button>';var isCustom=mode==='custom';for(var j=0;j<entries.length;j++){var e=entries[j]||{},esn=e.server_name||'';h+='<div class="rl-row"><span class="rl-arrow">→</span><select class="rl-sel" onchange="relaySetEntry(\''+gid+'\','+j+',\'server_name\',this.value)" title="选择目标服务器">';for(var k=0;k<allSrv.length;k++){h+='<option value="'+allSrv[k]+'"'+(allSrv[k]===esn?' selected':'')+'>'+allSrv[k]+'</option>'}h+='</select><span class="rl-lbl">群→服</span><label class="tg" title="群聊→服务器转发"><input type="checkbox" '+(e.group_to_mc===true?'checked':'')+' '+(isCustom?'':'disabled')+' onchange="relaySetEntry(\''+gid+'\','+j+',\'group_to_mc\',this.checked)"><span class="sl"></span></label><span class="rl-lbl">服→群</span><label class="tg" title="服务器→群聊转发"><input type="checkbox" '+(e.mc_to_group===true?'checked':'')+' '+(isCustom?'':'disabled')+' onchange="relaySetEntry(\''+gid+'\','+j+',\'mc_to_group\',this.checked)"><span class="sl"></span></label><span class="rl-lbl">必须 /msay 才允许转发</span><label class="tg" title="必须 /msay 才允许转发"><input type="checkbox" '+(e.require_msay===true?'checked':'')+' '+(isCustom?'':'disabled')+' onchange="relaySetEntry(\''+gid+'\','+j+',\'require_msay\',this.checked)"><span class="sl"></span></label>';if(isCustom){var hasGfmt=e.format_group!==undefined,hasMfmt=e.format_mc!==undefined;h+='<div class="fmt-row"><span class="fmt-title">群→服格式'+(hasGfmt?'':' <span style="color:var(--m);font-size:10px">(全局默认)</span>')+'</span>'+fmtEditor('format_group',e.format_group||gc.relay_fmt_group||'[QQ] {name}: {msg}',gid,j,true)+'</div><div class="fmt-row"><span class="fmt-title">服→群格式'+(hasMfmt?'':' <span style="color:var(--m);font-size:10px">(全局默认)</span>')+'</span>'+fmtEditor('format_mc',e.format_mc||gc.relay_fmt_mc||'[MC] {player}: {msg}',gid,j,true)+'</div>'};if(entries.length>1){h+='<button class="bd bsm" style="font-size:10px;padding:2px 6px" onclick="relayDelEntry(\''+gid+'\','+j+')" title="移除此绑定">✕</button>'}h+='</div>'}h+='</div>'}if(!has)h+='<div class="emp">暂无群聊</div>';document.getElementById("main").innerHTML=h}
async function relayGlobalSet(key,val){var b={};b[key]=typeof val==="boolean"?val:val;await pjt(A+"/config/relay",b);toast("已更新");loRe()}
async function relaySetMode(gid,mode){var entries=await fj(A+"/relay/"+gid);if(!entries.length)entries=[{server_name:"",group_to_mc:false,mc_to_group:false}];for(var i=0;i<entries.length;i++)entries[i].mode=mode;await pjt(A+"/relay/"+gid,entries);toast("已更新模式");loRe()}
async function relayAutoBind(){var g=await fj(A+"/groups?filter_web_mgmt=1"),all=await fj(A+"/relay/all");for(var id in g){var srvs=g[id]||[];if(srvs.length>0){var sn=srvs[0].server_name||srvs[0].name||'';if(sn){var exist=all[id]||[];if(!exist.some(function(e){return e.server_name===sn})){exist.push({server_name:sn,group_to_mc:false,mc_to_group:false,mode:'off'});await pjt(A+"/relay/"+id,exist)}}}}toast("已自动绑定");loRe()}
async function relayAddEntry(gid){var sn=prompt("输入要绑定的服务器名称");if(!sn)return;await pj(A+"/relay/"+gid,{server_name:sn.trim(),group_to_mc:false,mc_to_group:false,mode:'custom'});toast("已添加");loRe()}
async function relayDelEntry(gid,idx){if(!confirm("确定删除此绑定？"))return;var entries=await fj(A+"/relay/"+gid);if(idx<entries.length){entries.splice(idx,1);await pjt(A+"/relay/"+gid,entries);toast("已删除");loRe()}}
async function relaySetEntry(gid,idx,key,val){var entries=await fj(A+"/relay/"+gid);if(idx<entries.length){entries[idx][key]=typeof val==="boolean"?val:val;await pjt(A+"/relay/"+gid,entries);toast("已更新")}}
async function relaySetSrv(gid,name){await pjt(A+"/relay/"+gid,{server_name:name});toast("服务器已更新")}
async function relayReset(gid){await fetch(A+"/relay/"+gid,{method:"DELETE"});toast("已重置");loRe()}
/* 格式编辑器 */
function parseFmt(f){var r=[],re=/\{[a-z_]+\}/g,l=0,m;while((m=re.exec(f))!==null){if(m.index>l)r.push({t:'tx',v:f.slice(l,m.index)});r.push({t:'ph',v:m[0]});l=m.index+m[0].length}if(l<f.length)r.push({t:'tx',v:f.slice(l)});return r}
function fmtEditor(k,val,gid,j,custom){var gc=window._gc||{},p=parseFmt(val),cs='';for(var i=0;i<p.length;i++){var t=p[i].t==='ph'?'ph':'tx',lbl=p[i].v;if(t==='ph'){var ph={'{name}':'昵称','{msg}':'消息','{server}':'服务器','{player}':'MC玩家','{group}':'群名'}[lbl]||lbl;cs+='<span class="fmt-chip fc-ph" onclick="fmtChipRm(this)" title="占位符: '+lbl+'">'+lbl+'</span>'}else{cs+='<span class="fmt-chip fc-tx" onclick="fmtChipRm(this)" title="点击移除">'+lbl.replace(/</g,'&lt;')+'</span>'}}var ed='<div class="fmt-ed" data-k="'+k+'" data-g="'+(gid||'')+'" data-j="'+(j||0)+'" data-c="'+(custom?'1':'0')+'">'+cs;if(custom){var isGfmt=k==='fmt_group'||k==='format_group';ed+='<span class="fmt-add"><select onchange="fmtChipTmpl(this)" style="font-size:10px;padding:1px 4px;border:1px dashed var(--b);background:transparent;color:var(--m);border-radius:3px;cursor:pointer" title="选择预设模板"><option value="">📋 模板</option>'+(isGfmt?'<option value="'+gc.relay_fmt_group+'">全局默认: '+(gc.relay_fmt_group||'[QQ] {name}: {msg}')+'</option><option value="{name}: {msg}">昵称: 消息 （例: 小明: 大家好）</option><option value="[{server}] {name}: {msg}">[服务器] 昵称: 消息 （例: [生存服] 小明: 大家好）</option><option value="{msg}">仅消息内容 （例: 大家好）</option><option value="{name} 说: {msg}">昵称 说: 消息 （例: 小明 说: 大家好）</option>':'<option value="'+gc.relay_fmt_mc+'">全局默认: '+(gc.relay_fmt_mc||'[MC] {player}: {msg}')+'</option><option value="{player}: {msg}">玩家: 消息 （例: Steve: 大家好）</option><option value="[{server}] {player}: {msg}">[服务器] 玩家: 消息 （例: [生存服] Steve: 大家好）</option><option value="{msg}">仅消息内容 （例: 大家好）</option><option value="{player} 说: {msg}">玩家 说: 消息 （例: Steve 说: 大家好）</option>')+'</select>';ed+='<select onchange="fmtChipAdd(this)" style="font-size:10px;padding:1px 4px;border:1px dashed var(--b);background:transparent;color:var(--m);border-radius:3px;cursor:pointer"><option value="">+ 添加</option><option value="_txt">✏ 自定义文字</option><optgroup label="占位符（中文显示，内部英文）"><option value="{name}">昵称 {name}</option><option value="{msg}">消息内容 {msg}</option><option value="{server}">服务器名 {server}</option><option value="{player}">MC玩家 {player}</option><option value="{group}">群名 {group}</option></optgroup></select></span>'}ed+='</div>';return ed}
async function fmtChipTmpl(sel){var v=sel.value;if(!v){sel.selectedIndex=0;return}sel.selectedIndex=0;var ed=sel.closest('.fmt-ed'),k=ed.dataset.k,g=ed.dataset.g,j=parseInt(ed.dataset.j)||0;if(g)await relaySetEntry(g,j,k,v);else await relayGlobalSet('relay_'+k,v);loRe()}
async function fmtChipAdd(sel){var v=sel.value;if(!v){sel.selectedIndex=0;return}sel.selectedIndex=0;var ed=sel.closest('.fmt-ed'),k=ed.dataset.k,g=ed.dataset.g,j=parseInt(ed.dataset.j)||0;if(v==='_txt'){v=prompt('输入自定义文字');if(!v)return}var chips=Array.from(ed.querySelectorAll('.fmt-chip')),nv=chips.map(function(c){return c.textContent}).join('')+v;if(g)await relaySetEntry(g,j,k,nv);else await relayGlobalSet('relay_'+k,nv);loRe()}
async function fmtChipRm(el){var ed=el.closest('.fmt-ed'),k=ed.dataset.k,g=ed.dataset.g,j=parseInt(ed.dataset.j)||0,chips=Array.from(ed.querySelectorAll('.fmt-chip')),idx=chips.indexOf(el),nv='';for(var i=0;i<chips.length;i++)if(i!==idx)nv+=chips[i].textContent;if(g)await relaySetEntry(g,j,k,nv);else await relayGlobalSet('relay_'+k,nv);loRe()}
/* ====== 在线追踪 ====== */
async function loTr(){var g=await fj(A+"/groups?filter_web_mgmt=1"),all=await fj(A+"/tracker/all"),gc=await fj(A+"/config/tracker"),h='<div class="ct"><h3>全局追踪设置</h3><table><tr><th>监控</th><th>提醒</th><th>提醒节点(分钟)</th><th>游戏内提醒</th><th>自动踢出</th><th>踢出阈值</th><th>封禁时长</th><th>排行自动重置(小时)</th></tr><tr><td><label class="tg"><input type="checkbox" '+(gc.tracker_enabled?'checked':'')+' onchange="tkGlobalSet(\'tracker_enabled\',this.checked)"><span class="sl"></span></label></td><td><label class="tg"><input type="checkbox" '+(gc.tracker_notify?'checked':'')+' onchange="tkGlobalSet(\'tracker_notify\',this.checked)"><span class="sl"></span></label></td><td><input style="width:110px" value="'+(gc.tracker_notify_intervals||[]).join(',')+'" onchange="tkGlobalSet(\'tracker_notify_intervals\',this.value)"></td><td><label class="tg"><input type="checkbox" '+(gc.tracker_notify_game?'checked':'')+' onchange="tkGlobalSet(\'tracker_notify_game\',this.checked)"><span class="sl"></span></label></td><td><label class="tg"><input type="checkbox" '+(gc.tracker_kick_enabled?'checked':'')+' onchange="tkGlobalSet(\'tracker_kick_enabled\',this.checked)"><span class="sl"></span></label></td><td><input style="width:80px" value="'+gc.tracker_kick_threshold+'" onchange="tkGlobalSet(\'tracker_kick_threshold\',this.value)"></td><td><input style="width:70px" value="'+gc.tracker_ban_minutes+'" onchange="tkGlobalSet(\'tracker_ban_minutes\',this.value)"></td><td><input style="width:60px" value="'+(gc.ranking_reset_hours||0)+'" onchange="tkGlobalSet(\'ranking_reset_hours\',this.value)" title="0=不自动重置，24=每天，168=每周"></td></tr></table></div>';for(var id in g){var c=all[id]||{},srvs=g[id]||[],nm=gn(srvs),ov=Object.keys(c).length>0;h+='<div class="ct"><h3>'+(nm||('群 '+id))+'<span class="badge">'+(c.use_global?'使用全局':(ov?'已覆盖':'继承全局'))+'</span></h3><table><tr><th>提醒开关</th><th>提醒节点</th><th>游戏内提醒</th><th>踢出开关</th><th>踢出阈值</th><th>封禁时长</th><th>使用全局</th><th>操作</th></tr><tr><td><label class="tg"><input type="checkbox" '+(c.notify_enabled?'checked':'')+' onchange="tkSet(\''+id+'\',\'notify_enabled\',this.checked)"><span class="sl"></span></label></td><td><input style="width:110px" value="'+(c.notify_intervals||gc.tracker_notify_intervals||'')+'" onchange="tkSet(\''+id+'\',\'notify_intervals\',this.value)"></td><td><label class="tg"><input type="checkbox" '+(c.notify_in_game?'checked':'')+' onchange="tkSet(\''+id+'\',\'notify_in_game\',this.checked)"><span class="sl"></span></label></td><td><label class="tg"><input type="checkbox" '+(c.kick_enabled?'checked':'')+' onchange="tkSet(\''+id+'\',\'kick_enabled\',this.checked)"><span class="sl"></span></label></td><td><input style="width:80px" value="'+(c.kick_threshold||gc.tracker_kick_threshold||'')+'" onchange="tkSet(\''+id+'\',\'kick_threshold\',this.value)"></td><td><input style="width:70px" value="'+(c.ban_minutes!==undefined?c.ban_minutes:gc.tracker_ban_minutes)+'" onchange="tkSet(\''+id+'\',\'ban_minutes\',this.value)"></td><td><label class="tg"><input type="checkbox" '+(c.use_global!==false?'checked':'')+' onchange="tkSet(\''+id+'\',\'use_global\',this.checked)"><span class="sl"></span></label></td><td>'+(ov?'<button class="bd bsm" onclick="tkRs(\''+id+'\')">重置为全局</button>':'<span style="color:#555;font-size:10px">-</span>')+'</td></tr></table></div>'}if(!Object.keys(g).length)h+='<div class="emp">暂无群聊数据</div>';document.getElementById("main").innerHTML=h}
async function tkSet(gid,key,val){var b={};if(key==="notify_intervals"){try{b[key]=val.split(",").map(function(s){return parseInt(s.trim())}).filter(function(n){return!isNaN(n)})}catch(e){return}}else if(typeof val==="boolean")b[key]=val;else{var n=parseInt(val);if(!isNaN(n))b[key]=n}await pjt(A+"/tracker/"+gid,b);toast("已更新")}
async function tkGlobalSet(key,val){var b={};if(key==="tracker_notify_intervals"){try{b[key]=val.split(",").map(function(s){return parseInt(s.trim())}).filter(function(n){return!isNaN(n)})}catch(e){return}}else if(typeof val==="boolean")b[key]=val;else{var n=parseInt(val);if(!isNaN(n))b[key]=n}await pjt(A+"/config/tracker",b);toast("已更新全局追踪设置")}
async function tkRs(gid){await fetch(A+"/tracker/"+gid,{method:"DELETE"});toast("已重置");loTr()}
/* ====== 玩家管理 (可编辑) ====== */
async function loP(sq){var u=A+"/players";if(sq)u+="?search="+encodeURIComponent(sq);var p=await fj(u);var h='<div class="fb" style="margin-bottom:12px"><h3 style="margin:0">玩家管理 ('+(p?p.length:0)+'人)</h3><div class="if"><input placeholder="搜索 QQ号/MC ID..." style="width:220px" onkeyup="if(event.key===\'Enter\')loP(this.value)"><button class="b1 bsm" onclick="addPlayer()">+ 添加玩家</button><button class="bg bsm" onclick="importOnline()">从在线导入</button></div></div>';if(!p||!p.length){h+='<div class="emp">暂无玩家数据</div>';document.getElementById("main").innerHTML=h;return}h+='<div class="ct"><table><tr><th>QQ号</th><th>MC ID</th><th>积分</th><th>连续签到</th><th>最后签到</th><th>总在线时长</th><th>注册时间</th><th>操作</th></tr>';for(var i=0;i<p.length;i++){var r=p[i],dur=r.total_online_min?Math.floor(r.total_online_min/60)+"小时"+Math.floor(r.total_online_min%60)+"分钟":"-",ct=r.created_at?new Date(r.created_at*1000).toLocaleDateString("zh-CN"):"-";h+='<tr><td>'+r.qq_id+'</td><td><strong>'+(r.mc_id||"未绑定")+'</strong></td><td>'+r.points+'</td><td>'+(r.checkin_streak||0)+'天</td><td>'+(r.last_checkin_date||"-")+'</td><td>'+dur+'</td><td>'+ct+'</td><td><div class="ac"><button class="bp bsm" onclick="edPlayer(\''+r.qq_id+'\')">编辑</button><button class="bg bsm" onclick="edPlayerCmd(\''+r.qq_id+'\',\''+(r.mc_id||'').replace(/'/g,"\\'")+'\')">命令</button><button class="bd bsm" onclick="rmPlayer(\''+r.qq_id+'\')">删除</button></div></td></tr>'}h+='</table></div>';document.getElementById("main").innerHTML=h}
function edPlayer(qq){var mc="",pts=0,strk=0;var rows=document.querySelectorAll("tr");for(var i=0;i<rows.length;i++){var cells=rows[i].querySelectorAll("td");if(cells.length>=8&&cells[0].textContent.trim()===qq){mc=cells[1].textContent.trim();pts=parseInt(cells[2].textContent)||0;strk=parseInt(cells[3].textContent)||0;break}}var m='<div class="mbg" id="ep-m" onclick="if(event.target===this)this.remove()"><div class="mod"><h3>编辑玩家: '+qq+'</h3><div class="fr"><div class="fg"><label>QQ号</label><input id="ep-qq" value="'+qq+'" title="修改后将更换绑定的QQ号"></div><div class="fg"><label>MC ID（游戏ID）</label><input id="ep-mc" value="'+(mc==='未绑定'?'':mc)+'" title="修改绑定的MC游戏ID"></div></div><div class="fr"><div class="fg"><label>积分</label><input id="ep-pts" type="number" value="'+pts+'"></div><div class="fg"><label>连续签到天数</label><input id="ep-strk" type="number" value="'+strk+'"></div></div><div class="fr" style="margin-top:14px"><button class="b1 bs" onclick="doEdPlayer(\''+qq+'\')">保存修改</button><button class="b2 bs" onclick="document.getElementById(\'ep-m\').remove()">取消</button></div></div></div>';document.body.insertAdjacentHTML("beforeend",m)}
async function doEdPlayer(qq){var nqq=document.getElementById("ep-qq").value.trim(),b={mc_id:document.getElementById("ep-mc").value.trim(),points:parseInt(document.getElementById("ep-pts").value)||0,checkin_streak:parseInt(document.getElementById("ep-strk").value)||0};if(nqq&&nqq!==qq)b.new_qq_id=nqq;await pjt(A+"/players/"+qq,b);document.getElementById("ep-m")?.remove();toast("玩家信息已更新");loP()}
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
async function loOn(){var u=A+"/online";if(og)u+="?gid="+og;var o=await fj(u),rk=null;try{rk=await fj(A+"/online_ranking?limit=20")}catch(e){}var g=await fj(A+"/groups?filter_web_mgmt=1");var gOpts='<option value="">全部群聊</option>';for(var id in g){var nm=gn(g[id]);gOpts+='<option value="'+id+'" '+(id===og?'selected':'')+'>'+(nm||'群 '+id)+'</option>'}var h='<div class="fb" style="margin-bottom:14px"><h3 style="margin:0">当前在线玩家</h3><div style="display:flex;align-items:center;gap:8px"><select onchange="og=this.value;loOn()" style="width:160px">'+gOpts+'</select><button class="b2 bsm" onclick="refreshOnline()">刷新</button></div></div>';if(!o||!Object.keys(o).length){h+='<div class="emp">暂无玩家在线</div>'}else{var t=0;for(var k in o)t+=Object.keys(o[k]||{}).length;h+='<div style="color:var(--m);font-size:12px;margin-bottom:14px">共 '+t+' 名玩家在线</div>';for(var sid in o){var pl=o[sid]||{},kn=Object.keys(pl),sn=kn.length>0&&pl[kn[0]].server_name?pl[kn[0]].server_name:sid;h+='<div class="ct"><h3>🖥️ '+sn+'<span class="badge">'+kn.length+'人</span></h3><div class="oc-grid">';for(var nm in pl){var pp=pl[nm],mins=pp.session_minutes||0,hours=Math.floor(mins/60),rmins=mins%60,durTxt=hours>0?hours+"时"+rmins+"分":rmins+"分",pct=Math.min(100,mins>0?Math.round(mins/720*100):5),bgc=getAvatarColor(nm),loginAt=pp.login_at?new Date(pp.login_at*1000).toLocaleTimeString("zh-CN",{hour:"2-digit",minute:"2-digit"}):"-";h+='<div class="oc" onclick="showPlayerDetail(\''+nm.replace(/'/g,"\\'")+'\')" style="cursor:pointer" title="点击查看详情"><div class="oc-av" style="background:'+bgc+'">'+getInitials(nm)+'</div><div class="oc-info"><div class="oc-name">'+nm+'</div><div class="oc-dur">⏱ '+durTxt+' | 登录 '+loginAt+'</div><div class="oc-bar"><div class="oc-bar-fill" style="width:'+pct+'%;background:'+bgc+'"></div></div></div></div>'}h+='</div></div>'}}if(rk&&rk.length){h+='<div class="ct" style="margin-top:12px"><div class="fb" style="margin-bottom:8px"><h3 style="margin:0">📊 在线时长排行 Top20</h3><button class="bd bsm" onclick="resetRanking()">重置排行</button></div><table><tr><th>排名</th><th>服务器</th><th>玩家</th><th>总在线时长</th></tr>';for(var i=0;i<rk.length;i++){var r=rk[i],hh=Math.floor((r.total||0)/3600),mm=Math.floor(((r.total||0)%3600)/60);h+='<tr><td>'+(i+1)+'</td><td>'+(r.server_name||'-')+'</td><td>'+(r.player_name||'-')+'</td><td>'+hh+'小时'+mm+'分钟</td></tr>'}h+='</table></div>'}try{var oh=await fj(A+"/online_history?limit=70");if(oh&&oh.length){var maxM=1;for(var i=0;i<oh.length;i++){maxM=Math.max(maxM,oh[i].minutes||0)}h+='<div class="ct" style="margin-top:14px"><h3>📈 在线时长记录 (最近'+oh.length+'条)</h3><div class="oh-chart">';for(var i=0;i<oh.length;i++){var ri=oh[i],m=ri.minutes||0,hgt=Math.max(8,(m/maxM)*260),bgc=getAvatarColor(ri.player_name||"?"),mf=Math.floor(m),durTxt=mf>=60?Math.floor(mf/60)+'时'+(mf%60)+'分':mf+'分';h+='<div class="oh-bar" style="height:'+hgt+'px;background:'+bgc+'"><div class="oh-tip">'+ri.player_name+' @ '+(ri.server_name||'?')+'<br>'+ri.start_fmt+' ~ '+ri.end_fmt+'<br>'+durTxt+'</div></div>'}h+='</div></div>'}}catch(e){}document.getElementById("main").innerHTML=h;refresh(15000,loOn)}
async function refreshOnline(){toast("正在查询在线玩家...");try{var r=await pj(A+"/online/refresh",{});var parts=[];if(r.servers_ok>0)parts.push(r.servers_ok+"个服务器查询成功");if(r.servers_err>0)parts.push(r.servers_err+"个失败");parts.push("发现"+r.total_found+"人在线");toast("刷新完成: "+parts.join("，"))}catch(e){var msg=e.message;try{var j=JSON.parse(msg);msg=j.error||msg}catch(x){}toast(msg,true)}loOn()}
async function resetRanking(){if(!confirm("确定要重置所有在线时长排行数据吗？此操作不可撤销。"))return;try{var r=await pj(A+"/online_ranking/reset",{});toast("已重置，删除了 "+r.deleted+" 条记录");loOn()}catch(e){var msg=e.message;try{var j=JSON.parse(msg);msg=j.error||msg}catch(x){}toast(msg,true)}}
async function showPlayerDetail(playerName){var o=await fj(A+"/online");var sessions=[];var totalMin=0;for(var sid in o){var pl=o[sid]||{};if(pl[playerName]){var pp=pl[playerName];sessions.push({server:sid,login_at:pp.login_at,session_minutes:pp.session_minutes||0});totalMin+=pp.session_minutes||0}}var hh=Math.floor(totalMin/60),mm=totalMin%60;var h='<div class="mbg" id="pd-m" onclick="if(event.target===this)this.remove()"><div class="mod"><h3>👤 '+playerName+'</h3><p style="color:var(--m);margin-bottom:8px">当前总在线: '+hh+'小时'+mm+'分钟</p>';if(sessions.length>0){h+='<table><tr><th>服务器</th><th>登录时间</th><th>在线时长</th></tr>';for(var i=0;i<sessions.length;i++){var s=sessions[i],sh=Math.floor(s.session_minutes/60),sm=s.session_minutes%60,lt=s.login_at?new Date(s.login_at*1000).toLocaleString("zh-CN"):"-";h+='<tr><td>'+s.server+'</td><td>'+lt+'</td><td>'+sh+'时'+sm+'分</td></tr>'}h+='</table>'}else{h+='<p style="color:var(--m)">该玩家当前不在线</p>'}try{var rk=await fj(A+"/online_ranking?limit=50");if(rk){for(var i=0;i<rk.length;i++){if(rk[i].player_name===playerName){var rh=Math.floor((rk[i].total||0)/3600),rm=Math.floor(((rk[i].total||0)%3600)/60);h+='<p style="margin-top:10px;color:var(--s)">📊 历史总在线: '+rh+'小时'+rm+'分钟 (排名 #'+(i+1)+')</p>';break}}}var oh=await fj(A+"/online_history?limit=200");if(oh){var ph=[];for(var i=0;i<oh.length;i++){if(oh[i].player_name===playerName)ph.push(oh[i])}if(ph.length>0){h+='<h4 style="margin-top:12px;color:var(--a)">📜 最近在线记录</h4><table><tr><th>服务器</th><th>上线</th><th>下线</th><th>时长</th></tr>';for(var i=0;i<Math.min(ph.length,20);i++){var r=ph[i];h+='<tr><td>'+r.server_name+'</td><td>'+r.start_fmt+'</td><td>'+r.end_fmt+'</td><td>'+Math.floor(r.minutes)+'分钟</td></tr>'}h+='</table>'}}}catch(e){}h+='<button class="b2 bs" style="margin-top:12px" onclick="document.getElementById(\'pd-m\').remove()">关闭</button></div></div>';document.body.insertAdjacentHTML("beforeend",h)}
/* ====== 审计日志 ====== */
async function loAu(cat){cat=cat||"";var u=A+"/audit?limit=100";if(cat)u+="&category="+cat;var g=await fj(A+"/groups"),a=await fj(u),h='<div class="fb" style="margin-bottom:12px"><h3 style="margin:0">审计日志 (最近100条)</h3><button class="b2 bsm" onclick="loAu()">刷新</button></div><div class="fbar"><button class="bsm '+(cat===''?'bw':'b2')+'" onclick="loAu(\'\')">全部</button><button class="bsm '+(cat==='cmd'?'b1':'b2')+'" onclick="loAu(\'cmd\')">命令</button><button class="bsm '+(cat==='web'?'b1':'b2')+'" onclick="loAu(\'web\')">Web操作</button><button class="bsm '+(cat==='web_rcon'?'b1':'b2')+'" onclick="loAu(\'web_rcon\')">Web命令</button></div>';if(!a||!a.length){h+='<div class="emp">暂无审计日志</div>'}else{var catNames={cmd:"命令",web:"Web操作",web_rcon:"Web命令"};h+='<div class="ct"><table><tr><th>时间</th><th>类型</th><th>QQ号</th><th>昵称</th><th>群聊</th><th>操作</th><th>结果</th><th>详情</th></tr>';for(var i=0;i<a.length;i++){var r=a[i],ts=r.time?new Date(r.time*1000).toLocaleString("zh-CN"):"-",grp=gn(g[r.group_id]||[]),ct=r.category||"cmd",cn=catNames[ct]||ct;h+='<tr><td>'+ts+'</td><td><span class="badge" style="font-size:10px">'+cn+'</span></td><td>'+r.sender_id+'</td><td>'+r.sender_name+'</td><td>'+(grp||(r.group_id?'群 '+r.group_id:'-'))+'</td><td><code style="font-size:10px">'+r.cmd+'</code></td><td><span class="t1 '+(r.ok?'t-on':'t-off')+'">'+(r.ok?'成功':'失败')+'</span></td><td style="max-width:200px;font-size:10px">'+(r.resp||'').slice(0,80)+'</td></tr>'}h+='</table></div>'}document.getElementById("main").innerHTML=h;refresh(20000,loAu)}
/* ====== 宏命令 ====== */
async function loMa(){var m=await fj(A+"/macros"),h='<div class="fb" style="margin-bottom:12px"><h3 style="margin:0">宏命令管理</h3><button class="b1 bsm" onclick="adMac()">+ 新建宏</button></div>';for(var n in m){var mc=m[n],cmds=mc.commands||mc,en=mc.enabled!==false;h+='<div class="ct"><div style="display:flex;justify-content:space-between;align-items:flex-start"><div style="flex:1"><h3 style="margin:0 0 4px">'+n+'<label class="tg" style="margin-left:8px;vertical-align:middle"><input type="checkbox" '+(en?'checked':'')+' onchange="tglMa(\''+n.replace(/'/g,"\\'")+'\',this.checked)"><span class="sl"></span></label><span style="color:var(--m);font-size:10px;margin-left:6px">'+(en?'启用':'禁用')+'</span><span class="badge" style="margin-left:6px">'+cmds.length+'条命令</span></h3><pre style="margin:4px 0 0">'+cmds.join("\n")+'</pre></div><div class="ac"><button class="b1 bsm" onclick="execMacro(\''+n.replace(/'/g,"\\'")+'\')">▶ 执行</button><button class="bw bsm" onclick="edMac(\''+n.replace(/'/g,"\\'")+'\')">编辑</button><button class="bd bsm" onclick="rmMac(\''+n.replace(/'/g,"\\'")+'\')">删除</button></div></div></div>'}if(!Object.keys(m).length)h+='<div class="emp">暂无宏命令</div>';document.getElementById("main").innerHTML=h;window._macros=m}
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
function otModal(name,idx){var t={};if(idx!==undefined&&window._otriggers)t=window._otriggers[idx]||{};var isEdit=!!name;var m='<div class="mbg" id="ot-m" onclick="if(event.target===this)this.remove()"><div class="mod" style="max-width:600px"><h3>'+(isEdit?'编辑触发器':'新建上线触发器')+'</h3>';m+='<div class="fg"><label>触发器名称 *</label><input id="otn" value="'+(t.name||'')+'"></div>';m+='<div class="fg"><label>备注说明</label><input id="otnote" value="'+(t.note||'')+'" placeholder="如：自动设置移速 0.15"></div>';m+='<div class="fr"><div class="fg"><label>目标玩家名 *</label><input id="otpl" value="'+(t.player||'')+'" placeholder="MC 玩家 ID"></div><div class="fg"><label>匹配方式</label><select id="otmt"><option value="exact" '+(t.match_type!=='contains'?'selected':'')+'>精确匹配</option><option value="contains" '+(t.match_type==='contains'?'selected':'')+'>包含匹配</option></select></div></div>';m+='<div class="fg"><label>触发冷却(秒)</label><input type="number" id="otcd" value="'+(t.cooldown_seconds||300)+'" min="0"></div>';m+='<div class="fg"><label>命令列表(一行一条命令)<br><span style="color:var(--m);font-size:10px">{player} 将被替换为上线玩家名，如 /attribute {player} ... base set 0.15</span></label><textarea id="otc" rows="4" placeholder="/attribute {player} minecraft:generic.movement_speed base set 0.15">'+(t.commands||[]).join("\n")+'</textarea></div>';m+='<div style="margin-top:14px"><button class="b1 bs" onclick="saveOt(\''+(isEdit?t.name.replace(/'/g,"\\'"):'')+'\')">保存</button><button class="b2 bs" onclick="document.getElementById(\'ot-m\').remove()">取消</button></div></div></div>';document.body.insertAdjacentHTML("beforeend",m)}
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
async function loCfg(){var c=await fj(A+"/config/all"),h='<div class="ct sf"><h3>⚙️ 全局设置</h3><form id="cfg-form" onsubmit="return doSaveCfg()"><div class="sg">';h+='<div class="sg-item"><h4>🔐 管理员与安全</h4><div class="fg"><label>管理员QQ列表（每行一个QQ号）</label><textarea id="cfg-admin-qqs">'+((c.admin_qqs||[]).join("\n"))+'</textarea></div><div class="fr"><div class="fg"><label>RCON超时(秒)</label><input type="number" id="cfg-rcon-timeout" value="'+(c.rcon_timeout||5)+'"></div><div class="fg"><label>选服TTL(秒)</label><input type="number" id="cfg-select-ttl" value="'+(c.select_ttl||30)+'"></div></div></div>';h+='<div class="sg-item"><h4>⚡ 速率限制</h4><div class="fr"><div class="fg"><label>速率限制开关</label><select id="cfg-rate-enabled"><option value="1" '+(c.rate_enabled?'selected':'')+'>开启</option><option value="0" '+(!c.rate_enabled?'selected':'')+'>关闭</option></select></div><div class="fg"><label>基础间隔(毫秒)</label><input type="number" id="cfg-rate-base-ms" value="'+(c.rate_base_ms||1000)+'"></div></div><div class="fr"><div class="fg"><label>窗口时间(分钟)</label><input type="number" id="cfg-rate-window-minutes" value="'+Math.floor((c.rate_window_s||300)/60)+'"></div><div class="fg"><label>触发阈值(次数)</label><input type="number" id="cfg-rate-threshold" value="'+(c.rate_threshold||10)+'"></div></div><div class="fr"><div class="fg"><label>增量(毫秒)</label><input type="number" id="cfg-rate-increment-ms" value="'+(c.rate_increment_ms||500)+'"></div><div class="fg"><label>最大间隔(毫秒)</label><input type="number" id="cfg-rate-max-ms" value="'+(c.rate_max_ms||10000)+'"></div></div><div class="fr"><div class="fg"><label>自动恢复</label><select id="cfg-rate-auto-recovery"><option value="1" '+(c.rate_auto_recovery?'selected':'')+'>开启</option><option value="0" '+(!c.rate_auto_recovery?'selected':'')+'>关闭</option></select></div><div class="fg"><label>恢复时间(分钟)</label><input type="number" id="cfg-rate-recovery-minutes" value="'+Math.floor((c.rate_recovery_s||600)/60)+'"></div></div></div>';h+='<div class="sg-item"><h4>👤 玩家数据库</h4><div class="fr"><div class="fg"><label>玩家DB开关</label><select id="cfg-pdb-enabled"><option value="1" '+(c.pdb_enabled?'selected':'')+'>开启</option><option value="0" '+(!c.pdb_enabled?'selected':'')+'>关闭</option></select></div><div class="fg"><label>签到积分</label><input type="number" id="cfg-pdb-checkin-pts" value="'+(c.pdb_checkin_pts||10)+'"></div></div><div class="fr"><div class="fg"><label>连签加成</label><input type="number" id="cfg-pdb-streak-bonus" value="'+(c.pdb_streak_bonus||2)+'"></div><div class="fg"><label>新玩家积分</label><input type="number" id="cfg-pdb-new-pts" value="'+(c.pdb_new_pts||50)+'"></div></div><div class="fr"><div class="fg"><label>补偿功能</label><select id="cfg-pdb-comp-enabled"><option value="1" '+(c.pdb_comp_enabled?'selected':'')+'>开启</option><option value="0" '+(!c.pdb_comp_enabled?'selected':'')+'>关闭</option></select></div><div class="fg"><label>补偿冷却(小时)</label><input type="number" id="cfg-pdb-comp-cooldown" value="'+(c.pdb_comp_cooldown_hours||24)+'"></div></div><div class="fr"><div class="fg"><label>补偿白名单(每行一个QQ)</label><textarea id="cfg-pdb-comp-wl" rows="3">'+((c.pdb_comp_whitelist||[]).join("\n"))+'</textarea></div><div class="fg"><label>需管理员审批</label><select id="cfg-pdb-comp-admin"><option value="1" '+(c.pdb_comp_require_admin!==false?'selected':'')+'>是</option><option value="0" '+(c.pdb_comp_require_admin===false?'selected':'')+'>否</option></select></div></div><div class="fr"><div class="fg"><label>补偿命令黑名单(每行一个关键词)</label><textarea id="cfg-pdb-comp-bl" rows="3">'+((c.pdb_comp_blacklist||[]).join("\n"))+'</textarea></div></div></div>';h+='<div class="sg-item"><h4>🔍 在线追踪</h4><div class="fr"><div class="fg"><label>追踪开关</label><select id="cfg-tk-on"><option value="1" '+(c.tracker_enabled?'selected':'')+'>开启</option><option value="0" '+(!c.tracker_enabled?'selected':'')+'>关闭</option></select></div><div class="fg"><label>查询方式</label><select id="cfg-tk-method"><option value="rcon" '+((c.tracker_method||'rcon')==='rcon'?'selected':'')+'>RCON</option><option value="mcstatus" '+((c.tracker_method||'')==='mcstatus'?'selected':'')+'>MCStatus</option></select></div><div class="fg"><label>轮询间隔(秒)</label><input type="number" id="cfg-tk-interval" value="'+(c.tracker_interval||60)+'"></div></div><div class="fr"><div class="fg"><label>提醒开关</label><select id="cfg-tk-notify"><option value="1" '+(c.tracker_notify?'selected':'')+'>开启</option><option value="0" '+(!c.tracker_notify?'selected':'')+'>关闭</option></select></div><div class="fg"><label>提醒目标</label><select id="cfg-tk-target"><option value="group" '+((c.tracker_notify_target||'group')==='group'?'selected':'')+'>群聊</option><option value="admin_dm" '+((c.tracker_notify_target||'')==='admin_dm'?'selected':'')+'>管理员私聊</option></select></div><div class="fg"><label>提醒节点(分钟,逗号分隔)</label><input id="cfg-tk-intervals" value="'+(c.tracker_notify_intervals||[]).join(',')+'"></div></div><div class="fr"><div class="fg"><label>游戏内提醒</label><select id="cfg-tk-notify-game"><option value="1" '+(c.tracker_notify_game?'selected':'')+'>开启</option><option value="0" '+(!c.tracker_notify_game?'selected':'')+'>关闭</option></select></div><div class="fg"><label>游戏提醒格式</label><input id="cfg-tk-fmt-game" value="'+(c.tracker_notify_game_fmt||'')+'"></div><div class="fg"><label>自动踢出</label><select id="cfg-tk-kick"><option value="1" '+(c.tracker_kick_enabled?'selected':'')+'>开启</option><option value="0" '+(!c.tracker_kick_enabled?'selected':'')+'>关闭</option></select></div></div><div class="fr"><div class="fg"><label>踢出阈值(分钟)</label><input type="number" id="cfg-tk-threshold" value="'+(c.tracker_kick_threshold||720)+'"></div><div class="fg"><label>踢出原因</label><input id="cfg-tk-reason" value="'+(c.tracker_kick_reason||'')+'"></div><div class="fg"><label>封禁时长(分钟)</label><input type="number" id="cfg-tk-ban" value="'+(c.tracker_ban_minutes||30)+'"></div></div></div>';h+='<div class="sg-item"><h4>📡 查询显示</h4><div class="fr"><div class="fg"><label>地址端口</label><select id="cfg-sq-addr"><option value="1" '+(c.show_addr_port!==false?'selected':'')+'>显示</option><option value="0" '+(c.show_addr_port===false?'selected':'')+'>隐藏</option></select></div><div class="fg"><label>版本</label><select id="cfg-sq-ver"><option value="1" '+(c.show_ver!==false?'selected':'')+'>显示</option><option value="0" '+(c.show_ver===false?'selected':'')+'>隐藏</option></select></div><div class="fg"><label>延迟</label><select id="cfg-sq-lat"><option value="1" '+(c.show_lat!==false?'selected':'')+'>显示</option><option value="0" '+(c.show_lat===false?'selected':'')+'>隐藏</option></select></div></div><div class="fr"><div class="fg"><label>在线人数</label><select id="cfg-sq-on"><option value="1" '+(c.show_on!==false?'selected':'')+'>显示</option><option value="0" '+(c.show_on===false?'selected':'')+'>隐藏</option></select></div><div class="fg"><label>玩家列表</label><select id="cfg-sq-pl"><option value="1" '+(c.show_pl!==false?'selected':'')+'>显示</option><option value="0" '+(c.show_pl===false?'selected':'')+'>隐藏</option></select></div><div class="fg"><label>渲染为图片</label><select id="cfg-sq-img"><option value="1" '+(c.render_img?'selected':'')+'>开启</option><option value="0" '+(!c.render_img?'selected':'')+'>关闭</option></select></div></div><div class="fr"><div class="fg"><label>自动清理(天)</label><input type="number" id="cfg-sq-clean" value="'+(c.auto_cleanup_days||10)+'"></div></div></div>';h+='<div class="sg-item"><h4>💬 群服互联</h4><div class="fr"><div class="fg"><label>互联开关</label><select id="cfg-relay-on"><option value="1" '+(c.relay_enabled?'selected':'')+'>开启</option><option value="0" '+(!c.relay_enabled?'selected':'')+'>关闭</option></select></div><div class="fg"><label>群→MC</label><select id="cfg-relay-g2m"><option value="1" '+(c.relay_group_to_mc?'selected':'')+'>开启</option><option value="0" '+(!c.relay_group_to_mc?'selected':'')+'>关闭</option></select></div><div class="fg"><label>MC→群</label><select id="cfg-relay-m2g"><option value="1" '+(c.relay_mc_to_group?'selected':'')+'>开启</option><option value="0" '+(!c.relay_mc_to_group?'selected':'')+'>关闭</option></select></div></div><div class="fr"><div class="fg"><label>群→MC格式</label><input id="cfg-relay-fg" value="'+(c.relay_fmt_group||'')+'"></div><div class="fg"><label>MC→群格式</label><input id="cfg-relay-fm" value="'+(c.relay_fmt_mc||'')+'"></div></div></div>';h+='<div class="sg-item"><h4>🚫 危险命令黑名单（每行一个关键词）</h4><div class="fg"><textarea id="cfg-dangerous" rows="5">'+((c.dangerous_blacklist||[]).join("\n"))+'</textarea></div></div>';h+='<div class="sg-item"><h4>📁 通用</h4><div class="fr"><div class="fg"><label>脚本目录</label><input id="cfg-scripts-dir" value="'+(c.scripts_dir||'scripts')+'"></div></div>';h+='<div class="sg-item"><h4>🗄️ 数据库存储</h4><p style="font-size:11px;color:var(--m);margin-bottom:8px">玩家数据与在线记录共用同一数据库</p><div class="fr"><div class="fg"><label>存储模式</label><select id="cfg-pdb-storage-mode"><option value="local" '+((c.pdb_storage_mode||"local")=="local"?"selected":"")+'>仅本地</option><option value="external" '+((c.pdb_storage_mode||"")=="external"?"selected":"")+'>仅云端</option><option value="dual" '+((c.pdb_storage_mode||"")=="dual"?"selected":"")+'>双端</option></select></div><div class="fg"><label>读取来源</label><select id="cfg-pdb-read-source"><option value="local" '+((c.pdb_read_source||"local")=="local"?"selected":"")+'>本地</option><option value="external" '+((c.pdb_read_source||"")=="external"?"selected":"")+'>云端</option></select></div></div><div class="fr"><div class="fg"><label style="width:110px">云端DB路径 (SQLite)</label><input id="cfg-pdb-ext-db-path" value="'+(c.pdb_ext_db_path||"")+'" placeholder="如 D:/shared/mc_data.db"></div><div class="fg"><label style="width:110px">云端主机</label><input id="cfg-pdb-ext-host" value="'+(c.pdb_ext_host||"")+'" placeholder="127.0.0.1"></div></div><div class="fr"><div class="fg"><label style="width:110px">端口</label><input type="number" id="cfg-pdb-ext-port" value="'+(c.pdb_ext_port||3306)+'"></div><div class="fg"><label style="width:110px">用户名</label><input id="cfg-pdb-ext-user" value="'+(c.pdb_ext_user||"")+'" placeholder="root"></div></div><div class="fr"><div class="fg"><label style="width:110px">密码</label><input type="password" id="cfg-pdb-ext-password" value="'+(c.pdb_ext_password||"")+'" placeholder="留空不修改"></div><div class="fg"><label style="width:110px">数据库名</label><input id="cfg-pdb-ext-database" value="'+(c.pdb_ext_database||"")+'" placeholder="mc_players"></div></div><p style="font-size:10px;color:var(--m);margin-top:4px">云端数据库需插件重启后生效。双端模式同时存储到本地和云端</p></div>';h+='</div></div><div style="margin-top:20px;padding-top:16px;border-top:1px solid var(--b)"><button class="b1 bs" type="submit">💾 保存所有设置</button><button class="b2 bs" type="button" onclick="loCfg()" style="margin-left:8px">🔄 重新加载</button></div></form></div>';document.getElementById("main").innerHTML=h}
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
        tk_notify:document.getElementById("cfg-tk-notify").value=="1",
        tk_target:document.getElementById("cfg-tk-target").value,
        tk_intervals:document.getElementById("cfg-tk-intervals").value.split(",").map(function(s){return parseInt(s.trim())}).filter(function(n){return!isNaN(n)}),
        tk_notify_game:document.getElementById("cfg-tk-notify-game").value=="1",
        tk_fmt_game:document.getElementById("cfg-tk-fmt-game").value,
        tk_kick:document.getElementById("cfg-tk-kick").value=="1",
        tk_threshold:parseInt(document.getElementById("cfg-tk-threshold").value)||720,
        tk_reason:document.getElementById("cfg-tk-reason").value,
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
        scripts_dir:document.getElementById("cfg-scripts-dir").value.trim(),
        dangerous_blacklist:document.getElementById("cfg-dangerous").value.split("\n").map(function(s){return s.trim()}).filter(Boolean),
        online_db_storage_mode:document.getElementById("cfg-odb-mode").value,
        online_db_read_source:document.getElementById("cfg-odb-read").value,
        online_db_ext_path:document.getElementById("cfg-odb-path").value.trim()
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
try{chk()}catch(e){showErr("初始化: "+e.message)}
</script>
</body>
</html>"""


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
            return self._html(PANEL_HTML)
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
            category = params.get("category", [""])[0]
            return self._api_audit(limit, category)

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
                       "rcon_password", "game_port"):
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
        for list_field in ("whitelist_qqs", "public_commands"):
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
        return self._json(getattr(self.plugin, '_tracker_overrides', {}))

    def _api_tracker_get(self, gid: str) -> bytes:
        return self._json(getattr(self.plugin, '_tracker_overrides', {}).get(gid, {}))

    async def _api_tracker_set(self, gid: str, body: bytes) -> bytes:
        data = self._read_body(body)
        ov = getattr(self.plugin, '_tracker_overrides', {})
        entry = ov.setdefault(gid, {})
        mapping = {
            "notify_enabled": True, "notify_intervals": True,
            "notify_in_game": True, "kick_enabled": True,
            "kick_threshold": True, "ban_minutes": True,
        }
        for k, v in data.items():
            if k in mapping:
                entry[k] = v
        self.plugin._tracker_overrides = ov
        return self._json(entry)

    def _api_tracker_reset(self, gid: str) -> bytes:
        ov = getattr(self.plugin, '_tracker_overrides', {})
        ov.pop(gid, None)
        self.plugin._tracker_overrides = ov
        return self._json({"ok": True})

    # ==================== 配置 API ====================

    def _api_config_relay(self) -> bytes:
        p = self.plugin
        rc = p.config.get("relay", {})
        return self._json({
            "relay_enabled": p.relay_enabled,
            "relay_group_to_mc": p.relay_group_to_mc,
            "relay_mc_to_group": p.relay_mc_to_group,
            "relay_require_msay": p.relay_require_msay,
            "relay_fmt_group": p.relay_fmt_group,
            "relay_fmt_mc": p.relay_fmt_mc,
        })

    async def _api_config_relay_set(self, body: bytes) -> bytes:
        """PUT: 更新全局 relay 配置"""
        data = self._read_body(body)
        p = self.plugin
        rc = p.config.setdefault("relay", {})
        bool_map = {"relay_enabled": "relay_enabled", "relay_group_to_mc": "relay_group_to_mc", "relay_mc_to_group": "relay_mc_to_group", "relay_require_msay": "relay_require_msay"}
        for k, attr in bool_map.items():
            if k in data:
                rc[k] = bool(data[k])
                setattr(p, attr, rc[k])
        str_map = {"relay_fmt_group": "relay_fmt_group", "relay_fmt_mc": "relay_fmt_mc"}
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
            "ranking_reset_hours": p.ranking_reset_hours,
        })

    async def _api_config_tracker_set(self, body: bytes) -> bytes:
        """PUT: 更新全局追踪配置"""
        data = self._read_body(body)
        p = self.plugin
        tc = p.config.setdefault("online_tracker", {})
        bool_keys = ["tracker_enabled", "tracker_notify", "tracker_notify_game", "tracker_kick_enabled"]
        int_keys = ["tracker_kick_threshold", "tracker_ban_minutes"]
        for k in bool_keys:
            if k in data:
                tc[k.replace("tracker_", "")] = bool(data[k])
                setattr(p, k, bool(data[k]))
        for k in int_keys:
            if k in data:
                short = k.replace("tracker_", "")
                tc[short] = int(data[k])
                setattr(p, k, int(data[k]))
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
        p.config["online_tracker"] = tc
        p.config.save_config()
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
            "tracker_notify": tc.get("notify_enabled", False),
            "tracker_notify_target": tc.get("notify_target", "group"),
            "tracker_notify_intervals": tc.get("notify_intervals", []),
            "tracker_notify_game": tc.get("notify_in_game", False),
            "tracker_notify_game_fmt": tc.get("notify_game_format", ""),
            "tracker_kick_enabled": tc.get("auto_kick_enabled", False),
            "tracker_kick_threshold": tc.get("auto_kick_threshold", 720),
            "tracker_kick_reason": tc.get("auto_kick_reason", ""),
            "tracker_ban_minutes": tc.get("auto_kick_ban_minutes", 30),
            # relay (full config)
            "relay_enabled": rc.get("enabled", False),
            "relay_group_to_mc": rc.get("group_to_mc", True),
            "relay_mc_to_group": rc.get("mc_to_group", False),
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
            "scripts_dir": gc.get("scripts_dir", "scripts"),
            # dangerous
            "dangerous_blacklist": p.dangerous_blacklist,
            # online db
            "online_db_storage_mode": str(odb.get("storage_mode", "local") or "local"),
            "online_db_read_source": str(odb.get("read_source", "local") or "local"),
            "online_db_ext_path": str(odb.get("external_db_path", "") or ""),
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
                cursor.execute("SELECT * FROM players ORDER BY created_at DESC LIMIT ?", (limit,))
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
        new_qq_id = str(data.get("new_qq_id", "")).strip()
        upd = {"mc_id": mc_id if mc_id else None, "points": points, "checkin_streak": checkin_streak}
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
        if "scripts_dir" in data:
            gc["scripts_dir"] = str(data["scripts_dir"])
        # 在线追踪 (full fields)
        tc = cfg.setdefault("online_tracker", {})
        if "tracker_enabled" in data:
            tc["enabled"] = bool(data["tracker_enabled"])
            p.tracker_enabled = tc["enabled"]
        if "tracker_method" in data:
            tc["query_method"] = str(data["tracker_method"])
        if "tracker_interval" in data:
            tc["poll_interval_seconds"] = int(data["tracker_interval"])
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
        if "relay_fmt_group" in data:
            rc["format_group"] = str(data["relay_fmt_group"])
            p.relay_fmt_group = rc["format_group"]
        if "relay_fmt_mc" in data:
            rc["format_mc"] = str(data["relay_fmt_mc"])
        # 危险命令黑名单
        if "dangerous_blacklist" in data:
            cfg["dangerous_commands"] = [str(c).strip() for c in data["dangerous_blacklist"] if str(c).strip()]
            p.dangerous_blacklist = cfg["dangerous_commands"]
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
        from .transport import rcon_command
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
                resp = await rcon_command(s["rcon_host"], int(s["rcon_port"]), s["rcon_password"], cmd)
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
            # 过滤掉关闭 web 管理的群
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
        return self._json(result)

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

    def _api_audit(self, limit: int, category: str = "") -> bytes:
        af = getattr(self.plugin, 'audit_file', None)
        if not af or not os.path.exists(af):
            return self._json([])
        entries = []
        with open(af, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if category and entry.get("category", "cmd") != category:
                        continue
                    entries.append(entry)
                except json.JSONDecodeError:
                    continue
        entries.reverse()
        return self._json(entries[:limit])

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
        except Exception as e:
            logger.error(f"[mrcon] Web 保存配置失败: {e}")

    def _save_macros(self):
        try:
            self.plugin.config["macros"] = dict(self.plugin.macros)
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