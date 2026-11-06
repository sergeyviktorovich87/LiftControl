from django.core.files.uploadhandler import FileUploadHandler, StopUpload


class BoundedUploadHandler(FileUploadHandler):
    """Stop oversized streams before Django spools them to private temporary disk."""
    def handle_raw_input(self,input_data,META,content_length,boundary,encoding=None):
        self.total = 0
        self.files = 0
        self.limit = (20 if '/documents/' in self.request.path else 10)*1024*1024
        self.too_large = bool(content_length and content_length > self.limit+1024*1024)
    def new_file(self,*args,**kwargs):
        super().new_file(*args,**kwargs)
        self.files += 1
        if self.too_large or self.files > 1:
            raise StopUpload(connection_reset=True)
    def receive_data_chunk(self,raw_data,start):
        self.total += len(raw_data)
        if self.total > self.limit:
            raise StopUpload(connection_reset=True)
        return raw_data
    def file_complete(self,file_size):
        return None
