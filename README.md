# PDF Extractor

PDF Extractor is a tool for extracting text from PDF files and managing their metadata.

## Installation

Clone the repository:

```bash
git clone https://github.com/oreotamish/pdf-extractor.git
```

Build the Docker image:

```bash
docker build -t pdf_extractor:latest .
```

Run the Docker container:

```bash
docker-compose up -d
```

## Usage

Navigate to [http://localhost:8000/docs](http://localhost:8000/docs) to access the Swagger documentation for all APIs.

### Steps:

1. **Create Auth User**: Use the `/auth/` API endpoint to create an authentication user.

2. **Login**: Log in using the authentication details obtained from step 1.

3. **Upload PDF**: Use the `/pdf/upload` endpoint to upload a PDF file. The file will be stored in the database with metadata, and the `processed` column will be set to `"false"`.

4. **List PDFs**: Send a GET request to the `/pdf/` endpoint to retrieve a list of all uploaded PDFs.

5. **Get PDF Metadata**: Send a GET request to the `/pdf/metadata/{file_name}` endpoint to retrieve the metadata of a specific PDF file.

6. **Delete PDF**: Send a DELETE request to the `/pdf/delete/{file_name}` endpoint to delete a specific PDF file.

7. **Extract Text from PDF**: Send a POST request to the `/pdf/text/{file_name}` endpoint to extract text from an already uploaded PDF file. This will return a Redis key where the text is stored with a TTL of 10 minutes.

8. **Retrieve Text from Redis**: Use the Redis key obtained from step 7 to retrieve the text and TTL of the PDF file by hitting the `/pdf/text-redis/{file_name}` endpoint.

![Swagger Documentation](https://github.com/oreotamish/pdf-extractor/assets/91555341/39064fd2-7ce1-4316-b688-13e321b852bb)
