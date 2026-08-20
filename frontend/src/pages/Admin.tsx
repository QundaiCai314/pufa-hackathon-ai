import { useEffect, useState } from 'react';
import { Card, Col, Row, Statistic, Table, Tabs, Tag, Button, Drawer, List, message } from 'antd';
import ChatPage from './Chat';
import DocumentsPage from './Documents';
const API=process.env.REACT_APP_API_URL||'http://localhost:8000';
const req=async(token:string,path:string)=>{const r=await fetch(API+path,{headers:{Authorization:'Bearer '+token}});const d=await r.json();if(!r.ok)throw Error(d.detail||'请求失败');return d};
export default function AdminPage({token}:{token:string}){
 const [overview,setOverview]=useState<any>({}),[users,setUsers]=useState<any[]>([]),[leads,setLeads]=useState<any[]>([]),[detail,setDetail]=useState<any[]>([]),[open,setOpen]=useState(false);
 const load=async()=>{try{const [o,u,l]=await Promise.all([req(token,'/api/v1/admin/overview'),req(token,'/api/v1/admin/users'),req(token,'/api/v1/admin/leads')]);setOverview(o);setUsers(u.users);setLeads(l.leads)}catch(e:any){message.error(e.message)}};
 useEffect(()=>{load()},[token]);
 const show=async(id:string)=>{try{const d=await req(token,'/api/v1/admin/sessions/'+id);setDetail(d.messages);setOpen(true)}catch(e:any){message.error(e.message)}};
 const download=async(id:string)=>{try{const r=await fetch(API+'/api/v1/admin/leads/'+id+'/sales-plan.docx',{headers:{Authorization:'Bearer '+token}});if(!r.ok)throw Error('生成方案失败');const a=document.createElement('a');a.href=URL.createObjectURL(await r.blob());a.download='客户销售沟通方案.docx';a.click();URL.revokeObjectURL(a.href)}catch(e:any){message.error(e.message)}};
 const tabs=[
  {key:'dash',label:'数据看板',children:<><Row gutter={16}>{[['用户数',overview.users],['会话数',overview.sessions],['消息数',overview.messages]].map((x:any)=><Col span={8} key={x[0]}><Card><Statistic title={x[0]} value={x[1]||0}/></Card></Col>)}</Row><Card title="意向分布" style={{marginTop:16}}><List dataSource={overview.lead_distribution||[]} renderItem={(x:any)=><List.Item><Tag color={x.lead_level==='high'?'red':x.lead_level==='medium'?'orange':'default'}>{x.lead_level}</Tag>{x.count} 个会话</List.Item>}/></Card></>},
  {key:'users',label:'用户管理',children:<Table rowKey="id" dataSource={users} columns={[{title:'用户名',dataIndex:'username'},{title:'邮箱',dataIndex:'email'},{title:'身份',dataIndex:'user_type',render:(x:string)=><Tag>{x==='admin'?'管理用户':'客户'}</Tag>},{title:'状态',dataIndex:'is_active',render:(x:boolean)=>x?'正常':'停用'}]}/>},
  {key:'leads',label:'客户线索',children:<Table rowKey="id" dataSource={leads} columns={[{title:'客户',dataIndex:'username'},{title:'会话',dataIndex:'session_name'},{title:'分数',dataIndex:'lead_score'},{title:'等级',dataIndex:'lead_level',render:(x:string)=><Tag color={x==='high'?'red':x==='medium'?'orange':'default'}>{x}</Tag>},{title:'操作',render:(_:any,r:any)=><><Button onClick={()=>show(r.id)}>查看对话</Button><Button style={{marginLeft:8}} onClick={()=>download(r.id)}>销售方案</Button></>}]}/>},
  {key:'docs',label:'知识库管理',children:<DocumentsPage/>}, {key:'ai',label:'管理 AI 助手',children:<ChatPage token={token}/>}];
 return <><Tabs items={tabs}/><Drawer title="对话记录" width={640} open={open} onClose={()=>setOpen(false)}><List dataSource={detail} renderItem={(x:any)=><List.Item><b>{x.role==='user'?'客户':'AI'}：</b>{x.content}</List.Item>}/></Drawer></>;
}
