#!/usr/bin/env python
# coding: utf-8

# ### PDF Summarization and Keyword Extraction Pipeline Assignment

# In[3]:


import os
import json
import time
import psutil
from pymongo import MongoClient
import requests
from PyPDF2 import PdfReader
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize, sent_tokenize
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# Download NLTK data files
# 'punkt' is used for tokenizing text into sentences and words
# 'stopwords' is used to filter out common English words that don't contribute to keyword extraction

import nltk
nltk.download('punkt')
nltk.download('stopwords')

# MongoDB connection function
# This function connects to a MongoDB database and returns a reference to the 'pdf_documents' collection.
# We use MongoDB to store metadata, summary, and keywords for each PDF.

def connect_mongo():
    client = MongoClient("mongodb://localhost:27017/")
    db = client["pdf_database"]
    collection = db["pdf_documents"]
    return collection

# Function to download a PDF from a URL
# This function takes a PDF URL and downloads the file to the specified output folder.
# We use it to automate the download of PDFs from the dataset.

def download_pdf(pdf_url, output_folder):
    start_time = time.time()
    try:
        response = requests.get(pdf_url)
        filename = os.path.join(output_folder, pdf_url.split('/')[-1].split('?')[0])
        with open(filename, 'wb') as f:
            f.write(response.content)
        download_time = time.time() - start_time
        print(f"Downloaded {filename} in {download_time:.2f} seconds")
        return filename, download_time
    except Exception as e:
        print(f"Error downloading {pdf_url}: {e}")
        return None, 0

# Function to parse text from a PDF file
# This function reads the content of a PDF file and extracts text using PyPDF2.
# Extracting text from PDFs is essential for summarization and keyword extraction.

def parse_pdf(file_path):
    start_time = time.time()
    try:
        reader = PdfReader(file_path)
        text = ""
        for page_num in range(len(reader.pages)):
            page_text = reader.pages[page_num].extract_text()
            text += page_text if page_text else ""
        parsing_time = time.time() - start_time
        print(f"Parsed {file_path} in {parsing_time:.2f} seconds. Extracted Text: {text[:100]}...")
        return text, parsing_time
    except Exception as e:
        print(f"Error parsing {file_path}: {e}")
        return None, 0

# Function to summarize text
# This function summarizes the extracted PDF text by taking the first 5 sentences.
# Summarization helps in giving a brief overview of the content.

def custom_summarize_text(text):
    word_frequencies = {}
    words = word_tokenize(text)
    for word in words:
        if word.isalnum():
            word_frequencies[word] = word_frequencies.get(word, 0) + 1
    sentences = sent_tokenize(text)
    sentence_scores = {}
    for sentence in sentences:
        for word in word_tokenize(sentence.lower()):
            if word in word_frequencies:
                if len(sentence.split(' ')) < 30:
                    sentence_scores[sentence] = sentence_scores.get(sentence, 0) + word_frequencies[word]
    sorted_sentences = sorted(sentence_scores, key=sentence_scores.get, reverse=True)
    return " ".join(sorted_sentences[:5])

# Function to extract keywords from text
# This function extracts the top 'num_keywords' from the text by frequency, excluding common stopwords.
# Keywords help in identifying the main topics of the document.

def custom_extract_keywords(text, num_keywords=5):
    words = word_tokenize(text.lower())
    stop_words = set(stopwords.words('english'))
    filtered_words = [word for word in words if word.isalnum() and word not in stop_words]
    tf = {}
    for word in filtered_words:
        tf[word] = tf.get(word, 0) + 1
    sorted_keywords = sorted(tf.items(), key=lambda x: x[1], reverse=True)
    return [word for word, freq in sorted_keywords[:num_keywords]]

# Function to store initial data in MongoDB
# This function stores basic metadata about the PDF (file name, size, path) in MongoDB before any processing.

def store_initial_data_in_mongo(file_path, collection):
    file_metadata = {
        "document_name": os.path.basename(file_path),
        "path": file_path,
        "size": os.path.getsize(file_path),
        "ingestion_date": datetime.utcnow(),
        "summary": None,
        "keywords": None
    }
    collection.insert_one(file_metadata)
    return file_metadata

# Function to update MongoDB with summary and keywords
# This function updates the MongoDB document with the generated summary and keywords.

def update_mongo_with_summary(file_metadata, summary, keywords, collection):
    query = {"path": file_metadata["path"]}
    update = {"$set": {"summary": summary, "keywords": keywords}}
    collection.update_one(query, update)

# Function to process a single PDF (download, parse, summarize, extract keywords)
def process_single_pdf(pdf_url, output_folder, collection, metrics):
    file_path, download_time = download_pdf(pdf_url, output_folder)
    if not file_path:
        return
    metrics['total_download_time'] += download_time
    
    text, parsing_time = parse_pdf(file_path)
    if not text:
        return
    metrics['total_parsing_time'] += parsing_time

    file_metadata = store_initial_data_in_mongo(file_path, collection)
    summary = custom_summarize_text(text)
    keywords = custom_extract_keywords(text)
    update_mongo_with_summary(file_metadata, summary, keywords, collection)

    # Track memory usage
    memory_usage = psutil.virtual_memory().used / (1024 * 1024)
    metrics['total_memory_usage'] += memory_usage

# Main function to process PDFs from dataset
# This function orchestrates the entire process: downloading PDFs, parsing, summarizing, extracting keywords, and storing the data.

def process_pdfs_concurrently(dataset_file, output_folder):
    with open(dataset_file, 'r') as f:
        dataset = json.load(f)

    # Connect to MongoDB
    collection = connect_mongo()

    # Initialize metrics
    metrics = {
        'total_download_time': 0,
        'total_parsing_time': 0,
        'total_memory_usage': 0,
        'pdf_count': 0
    }

    with ThreadPoolExecutor() as executor:
        futures = [executor.submit(process_single_pdf, pdf_url, output_folder, collection, metrics) for pdf_name, pdf_url in dataset.items()]
        for future in futures:
            future.result()
            metrics['pdf_count'] += 1

    # Display metrics
    print("All PDFs processed and stored.")
    if metrics['pdf_count'] > 0:
        print(f"Total Download Time: {metrics['total_download_time']:.2f} seconds")
        print(f"Total Parsing Time: {metrics['total_parsing_time']:.2f} seconds")
        print(f"Average Memory Usage: {metrics['total_memory_usage'] / metrics['pdf_count']:.2f} MB")

# Set the path to the dataset file and output folder
dataset_file = r"C:\Users\SUSRITA\OneDrive\Documents\Wasseroff\Dataset.json"
output_folder = r"C:\Users\SUSRITA\OneDrive\Documents\Downloaded_pdfs"

if not os.path.exists(output_folder):
    os.makedirs(output_folder)

# Run the pipeline
process_pdfs_concurrently(dataset_file, output_folder)


# In[ ]:




