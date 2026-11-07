import 'dart:convert';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

abstract class SecretStore {
  Future<String?> read(String key);
  Future<void> write(String key, String value);
  Future<void> clear();
  Future<void> delete(String key);
}

class DeviceStore implements SecretStore {
  final FlutterSecureStorage _storage = const FlutterSecureStorage();
  @override
  Future<String?> read(String key) => _storage.read(key: key);
  @override
  Future<void> write(String key, String value) =>
      _storage.write(key: key, value: value);
  @override
  Future<void> clear() => _storage.deleteAll();
  @override
  Future<void> delete(String key) => _storage.delete(key: key);
}

class MemoryStore implements SecretStore {
  final Map<String, String> values = {};
  @override
  Future<String?> read(String key) async => values[key];
  @override
  Future<void> write(String key, String value) async {
    values[key] = value;
  }

  @override
  Future<void> clear() async {
    values.clear();
  }

  @override
  Future<void> delete(String key) async {
    values.remove(key);
  }
}

String storageScope(Uri server, int user, int organization) =>
    '${base64Url.encode(utf8.encode(server.origin))}_${user}_$organization';
