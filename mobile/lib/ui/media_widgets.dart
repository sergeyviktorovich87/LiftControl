import 'dart:typed_data';
import 'package:flutter/material.dart';
import '../core/api.dart';
import '../core/controller.dart';
import 'common.dart';
import 'platform_bridge.dart';

class PrivateMedia extends StatefulWidget {
  const PrivateMedia({super.key,required this.controller,required this.organization,required this.attachment});
  final LiftController controller;
  final int organization;
  final Json attachment;
  @override
  State<PrivateMedia> createState()=>_PrivateMediaState();
}

class _PrivateMediaState extends State<PrivateMedia> {
  Future<Uint8List>? _image;
  bool _busy=false;
  bool get video => text(widget.attachment,'content_type','').startsWith('video/');
  @override
  void initState(){super.initState();if(!video)_image=widget.controller.download(text(widget.attachment,'url'),widget.organization);}
  Future<void> _play() async {
    if(_busy)return;
    setState(()=>_busy=true);
    try {
      final bytes=await widget.controller.download(text(widget.attachment,'url'),widget.organization,video:true);
      if(!mounted||!widget.controller.loggedIn||widget.controller.organization!=widget.organization)return;
      await PlatformBridge.openVideo(bytes,text(widget.attachment,'content_type'));
    }catch(e){if(mounted)showError(context,e);}
    finally{if(mounted)setState(()=>_busy=false);}
  }
  @override
  Widget build(BuildContext context){
    if(video)return ListTile(contentPadding:EdgeInsets.zero,leading:const Icon(Icons.play_circle_outline),
      title:const Text('Видео'),subtitle:Text('${((widget.attachment['size'] as num? ?? 0)/1024/1024).toStringAsFixed(1)} МБ'),
      trailing:_busy?const SizedBox(width:20,height:20,child:CircularProgressIndicator(strokeWidth:2)):null,
      onTap:widget.controller.canWrite&&!_busy?_play:null);
    return FutureBuilder<Uint8List>(future:_image,builder:(context,result){
      if(result.hasError)return const Padding(padding:EdgeInsets.all(8),child:Text('Фото недоступно. Проверьте связь и откройте чат заново.'));
      if(!result.hasData)return const SizedBox(height:100,child:Center(child:CircularProgressIndicator()));
      return Padding(padding:const EdgeInsets.symmetric(vertical:6),child:InkWell(
        onTap:()=>Navigator.push(context,MaterialPageRoute<void>(builder:(_)=>ScopePage(controller:widget.controller,organization:widget.organization,
          builder:(context)=>Scaffold(appBar:AppBar(title:const Text('Фото')),body:Center(child:InteractiveViewer(child:Image.memory(result.data!,cacheWidth:2000))))))),
        child:ClipRRect(borderRadius:BorderRadius.circular(12),child:Image.memory(result.data!,cacheWidth:800,fit:BoxFit.contain,height:200))));
    });
  }
}
