import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

const apiBase = String.fromEnvironment('API_BASE_URL', defaultValue: 'http://10.0.2.2:8000/api');

void main() => runApp(const LiftControlApp());

class LiftControlApp extends StatelessWidget {
  const LiftControlApp({super.key});
  @override Widget build(BuildContext context) => MaterialApp(debugShowCheckedModeBanner:false,title:'LiftControl',theme:ThemeData(colorScheme:ColorScheme.fromSeed(seedColor:Colors.blue),useMaterial3:true),home:const HomeScreen());
}

class HomeScreen extends StatefulWidget { const HomeScreen({super.key}); @override State<HomeScreen> createState()=>_HomeScreenState(); }
class _HomeScreenState extends State<HomeScreen>{
  List<dynamic> tickets=[]; bool loading=true; String? error;
  @override void initState(){super.initState();load();}
  Future<void> load() async { try{final r=await http.get(Uri.parse('$apiBase/tickets/')); if(r.statusCode!=200) throw Exception('HTTP ${r.statusCode}'); final j=jsonDecode(utf8.decode(r.bodyBytes)); setState((){tickets=j is List?j:(j['results']??[]);loading=false;error=null;});}catch(e){setState((){loading=false;error='Нет связи с сервером: $e';});}}
  @override Widget build(BuildContext context)=>Scaffold(appBar:AppBar(title:const Text('LiftControl'),actions:[IconButton(onPressed:load,icon:const Icon(Icons.refresh))]),body:RefreshIndicator(onRefresh:load,child:loading?const Center(child:CircularProgressIndicator()):error!=null?ListView(children:[Padding(padding:const EdgeInsets.all(24),child:Text(error!,style:const TextStyle(color:Colors.red)))]):ListView.builder(padding:const EdgeInsets.all(12),itemCount:tickets.length,itemBuilder:(c,i){final t=tickets[i] as Map<String,dynamic>;return Card(child:ListTile(leading:CircleAvatar(child:Text('${t['id']}')),title:Text(t['title']??'Заявка'),subtitle:Text('${t['address']??''}\nЛифт: ${t['elevator_factory_number']??'—'}'),isThreeLine:true,trailing:Chip(label:Text(t['status_display']??t['status']??''))));})),bottomNavigationBar:NavigationBar(selectedIndex:0,destinations:const [NavigationDestination(icon:Icon(Icons.assignment_outlined),label:'Заявки'),NavigationDestination(icon:Icon(Icons.map_outlined),label:'Маршрут'),NavigationDestination(icon:Icon(Icons.person_outline),label:'Профиль')])) ;
}
