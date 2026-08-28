import os
import re
import uuid
import json
import tempfile
from io import BytesIO
from pathlib import Path

try:
    from fastapi import UploadFile, Headers
except ImportError:
    from fastapi import UploadFile
    from starlette.datastructures import Headers

# Import our pipeline components
import sys
sys.path.insert(0, "/app/backend/data/anydoc_py")

from filtration_layer import FiltrationLayer, ComplexityLevel, analyze_file_complexity
from anydoc_markdown_converter import AnyDocMarkdownConverter, ConversionResult


def _safe_name(title: str) -> str:
    name = re.sub(r"[^\w\- ]+", "", title or "file").strip().replace(" ", "_")
    return (name or "file")[:80]


class Tools:
    def __init__(self):
        # Initialize the converter once
        self.converter = AnyDocMarkdownConverter(enable_ocr=False, enable_vision=False)
        self.filtration = FiltrationLayer()
    
    async def anydoc_to_markdown(
        self,
        file_id: str,
        extract_images: bool = True,
        extract_tables: bool = True,
        include_complexity_report: bool = True,
        __user__: dict = None,
        __event_emitter__=None,
        __request__=None,
    ) -> dict:
        """
        Convert any document to Markdown using the intelligent filtration pipeline.
        
        This tool:
        1. Takes a file_id from OpenWebUI Files
        2. Analyzes file complexity (images, tables, scanned content, etc.)
        3. Routes to optimal converter (fast path for simple, full pipeline for complex)
        4. Returns clean Markdown with extracted content
        
        Parameters:
        - file_id: The OpenWebUI file ID to convert (from file upload)
        - extract_images: Extract and embed images in markdown (default: true)
        - extract_tables: Extract and convert tables to markdown (default: true)
        - include_complexity_report: Include the filtration analysis in response (default: true)
        
        Returns: Markdown content with metadata about the conversion
        """
        if not file_id:
            return {"error": "file_id is required. Upload a file first, then pass its ID to this tool."}
        
        # Get the file from OpenWebUI Files API
        file_data = await self._get_file_by_id(file_id, __request__, __user__)
        if not file_data:
            return {"error": f"Could not retrieve file with ID: {file_id}"}
        
        file_bytes, filename, content_type = file_data
        
        # Save to temp file for processing
        suffix = Path(filename).suffix
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
        
        try:
            # Step 1: Filtration - Analyze complexity
            complexity_report = analyze_file_complexity(tmp_path)
            
            # Step 2: Convert using intelligent pipeline
            result = self.converter.convert(
                tmp_path,
                extract_images=extract_images,
                extract_tables=extract_tables,
                image_output_dir="/tmp/anydoc_images"
            )
            
            # Step 3: Prepare response
            response = {
                "success": result.success,
                "markdown": result.markdown if result.success else "",
                "extraction_method": result.extraction_method,
                "metadata": result.metadata,
                "images_extracted": len(result.images_extracted),
                "tables_extracted": len(result.tables_extracted),
            }
            
            if include_complexity_report and result.complexity_report:
                response["complexity_analysis"] = {
                    "level": result.complexity_report.complexity_level.value,
                    "score": result.complexity_report.complexity_score,
                    "factors": result.complexity_report.factors,
                    "recommendations": result.complexity_report.recommendations,
                    "metadata": result.complexity_report.metadata,
                }
            
            if not result.success:
                response["error"] = result.error
            
            # Optionally save markdown as a file in OpenWebUI
            if result.success and result.markdown:
                md_filename = f"{_safe_name(Path(filename).stem)}.md"
                md_file_id = await self._save_markdown_file(
                    result.markdown, md_filename, __request__, __user__
                )
                if md_file_id:
                    response["markdown_file_id"] = md_file_id
                    response["markdown_download_url"] = f"/api/v1/files/{md_file_id}/content"
            
            return response
            
        finally:
            # Cleanup temp file
            try:
                os.unlink(tmp_path)
            except:
                pass
    
    async def analyze_document_complexity(
        self,
        file_id: str,
        __user__: dict = None,
        __event_emitter__=None,
        __request__=None,
    ) -> dict:
        """
        Analyze a document's complexity WITHOUT converting it.
        
        Use this to understand what processing a file will need before converting.
        Returns detailed complexity report with routing recommendations.
        
        Parameters:
        - file_id: The OpenWebUI file ID to analyze
        
        Returns: Complexity analysis report
        """
        if not file_id:
            return {"error": "file_id is required"}
        
        file_data = await self._get_file_by_id(file_id, __request__, __user__)
        if not file_data:
            return {"error": f"Could not retrieve file with ID: {file_id}"}
        
        file_bytes, filename, content_type = file_data
        
        suffix = Path(filename).suffix
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
        
        try:
            report = analyze_file_complexity(tmp_path)
            return {
                "file_id": file_id,
                "filename": filename,
                "content_type": content_type,
                "complexity_level": report.complexity_level.value,
                "complexity_score": report.complexity_score,
                "factors": report.factors,
                "recommendations": report.recommendations,
                "metadata": report.metadata,
                "routing_decision": self._get_routing_decision(report)
            }
        finally:
            try:
                os.unlink(tmp_path)
            except:
                pass
    
    async def batch_convert_to_markdown(
        self,
        file_ids: list,
        extract_images: bool = True,
        extract_tables: bool = True,
        __user__: dict = None,
        __event_emitter__=None,
        __request__=None,
    ) -> dict:
        """
        Convert multiple documents to Markdown in one call.
        
        Parameters:
        - file_ids: List of OpenWebUI file IDs to convert
        - extract_images: Extract images (default: true)
        - extract_tables: Extract tables (default: true)
        
        Returns: List of conversion results
        """
        if not file_ids:
            return {"error": "file_ids list is required"}
        
        results = []
        for fid in file_ids:
            result = await self.anydoc_to_markdown(
                file_id=fid,
                extract_images=extract_images,
                extract_tables=extract_tables,
                include_complexity_report=True,
                __user__=__user__,
                __event_emitter__=__event_emitter__,
                __request__=__request__
            )
            results.append({"file_id": fid, **result})
        
        return {"results": results, "total": len(results), "successful": sum(1 for r in results if r.get("success"))}
    
    def _get_routing_decision(self, report) -> dict:
        """Determine the processing route based on complexity."""
        if report.complexity_level == ComplexityLevel.SIMPLE:
            return {
                "route": "fast_path",
                "description": "Direct to markdown conversion (pymupdf4llm/unstructured)",
                "estimated_time": "seconds",
                "backends": ["pymupdf4llm", "unstructured", "python-docx", "openpyxl"]
            }
        elif report.complexity_level == ComplexityLevel.MODERATE:
            return {
                "route": "enhanced_path",
                "description": "Enhanced extraction with table/image handling",
                "estimated_time": "10-30 seconds",
                "backends": ["pymupdf4llm + tables", "python-docx enhanced", "python-pptx"]
            }
        else:
            return {
                "route": "full_pipeline",
                "description": "Full extraction pipeline (OCR, layout analysis, image processing)",
                "estimated_time": "30-120 seconds",
                "backends": ["marker-pdf (if available)", "pymupdf4llm with OCR", "pytesseract for images"]
            }
    
    async def _get_file_by_id(self, file_id: str, request, user) -> tuple:
        """Retrieve file bytes from OpenWebUI Files API."""
        try:
            from open_webui.models.files import Files
            
            file_model = Files.get_file_by_id(file_id)
            if not file_model:
                return None
            
            # Get file path
            file_path = file_model.path
            if not file_path or not os.path.exists(file_path):
                # Try alternative path
                file_path = f"/app/backend/data/uploads/{file_id}"
                if not os.path.exists(file_path):
                    return None
            
            with open(file_path, "rb") as f:
                file_bytes = f.read()
            
            return (file_bytes, file_model.filename, file_model.meta.get("content_type", "application/octet-stream") if file_model.meta else "application/octet-stream")
        except Exception as e:
            # Fallback: try direct path
            try:
                fallback_path = f"/app/backend/data/uploads/{file_id}"
                if os.path.exists(fallback_path):
                    with open(fallback_path, "rb") as f:
                        file_bytes = f.read()
                    return (file_bytes, f"file_{file_id}", "application/octet-stream")
            except:
                pass
            return None
    
    async def _save_markdown_file(self, markdown: str, filename: str, request, user) -> str:
        """Save markdown as a file in OpenWebUI Files."""
        try:
            from open_webui.routers.files import upload_file_handler
            from open_webui.models.users import Users
            
            user_model = await Users.get_user_by_id(__user__["id"]) if __user__ else None
            if not user_model or not request:
                return None
            
            data = markdown.encode("utf-8")
            upload = UploadFile(
                file=BytesIO(data),
                filename=filename,
                headers=Headers({"content-type": "text/markdown"}),
            )
            
            item = await upload_file_handler(
                request=request,
                file=upload,
                metadata={"tags": ["generated", "markdown", "anydoc"]},
                process=False,
                user=user_model,
            )
            
            if item and getattr(item, "id", None):
                return item.id
        except Exception:
            pass
        return None


# Also provide a simpler tool for direct file upload conversion
class Tools:
    def __init__(self):
        self.converter = AnyDocMarkdownConverter(enable_ocr=False, enable_vision=False)
        self.filtration = FiltrationLayer()
    
    async def convert_uploaded_file_to_markdown(
        self,
        file: UploadFile,
        extract_images: bool = True,
        extract_tables: bool = True,
        include_complexity_report: bool = True,
        __user__: dict = None,
        __event_emitter__=None,
        __request__=None,
    ) -> dict:
        """
        Convert an uploaded file directly to Markdown.
        
        Use this when the user uploads a file in the chat and wants it converted.
        The file is passed directly as an UploadFile parameter.
        
        Parameters:
        - file: The uploaded file (automatically handled by OpenWebUI)
        - extract_images: Extract and reference images (default: true)
        - extract_tables: Convert tables to markdown (default: true)
        - include_complexity_report: Include analysis details (default: true)
        
        Returns: Markdown content with conversion metadata
        """
        if not file:
            return {"error": "No file uploaded"}
        
        # Read file content
        file_bytes = await file.read()
        filename = file.filename or "uploaded_file"
        content_type = file.content_type or "application/octet-stream"
        
        # Save to temp file
        suffix = Path(filename).suffix
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
        
        try:
            # Analyze complexity
            complexity_report = analyze_file_complexity(tmp_path)
            
            # Convert
            result = self.converter.convert(
                tmp_path,
                extract_images=extract_images,
                extract_tables=extract_tables,
                image_output_dir="/tmp/anydoc_images"
            )
            
            response = {
                "success": result.success,
                "markdown": result.markdown if result.success else "",
                "extraction_method": result.extraction_method,
                "metadata": result.metadata,
                "images_extracted": len(result.images_extracted),
                "tables_extracted": len(result.tables_extracted),
                "original_filename": filename,
                "original_content_type": content_type,
            }
            
            if include_complexity_report and result.complexity_report:
                response["complexity_analysis"] = {
                    "level": result.complexity_report.complexity_level.value,
                    "score": result.complexity_report.complexity_score,
                    "factors": result.complexity_report.factors,
                    "recommendations": result.complexity_report.recommendations,
                    "metadata": result.complexity_report.metadata,
                }
                response["routing_decision"] = self._get_routing_decision(result.complexity_report)
            
            if not result.success:
                response["error"] = result.error
            
            # Save markdown as downloadable file
            if result.success and result.markdown:
                md_filename = f"{_safe_name(Path(filename).stem)}.md"
                md_file_id = await self._save_markdown_file(
                    result.markdown, md_filename, __request__, __user__
                )
                if md_file_id:
                    response["markdown_file_id"] = md_file_id
                    response["markdown_download_url"] = f"/api/v1/files/{md_file_id}/content"
            
            return response
            
        finally:
            try:
                os.unlink(tmp_path)
            except:
                pass
    
    def _get_routing_decision(self, report) -> dict:
        if report.complexity_level == ComplexityLevel.SIMPLE:
            return {"route": "fast_path", "description": "Direct markdown conversion", "backends": ["pymupdf4llm", "unstructured"]}
        elif report.complexity_level == ComplexityLevel.MODERATE:
            return {"route": "enhanced_path", "description": "Enhanced extraction with tables/images", "backends": ["pymupdf4llm+enhanced", "python-docx"]}
        else:
            return {"route": "full_pipeline", "description": "Full OCR/layout analysis pipeline", "backends": ["marker-pdf", "pymupdf4llm+OCR"]}
    
    async def _save_markdown_file(self, markdown: str, filename: str, request, user) -> str:
        try:
            from open_webui.routers.files import upload_file_handler
            from open_webui.models.users import Users
            
            user_model = await Users.get_user_by_id(user["id"]) if user else None
            if not user_model or not request:
                return None
            
            data = markdown.encode("utf-8")
            upload = UploadFile(
                file=BytesIO(data),
                filename=filename,
                headers=Headers({"content-type": "text/markdown"}),
            )
            
            item = await upload_file_handler(
                request=request,
                file=upload,
                metadata={"tags": ["generated", "markdown", "anydoc"]},
                process=False,
                user=user_model,
            )
            return item.id if item and getattr(item, "id", None) else None
        except Exception:
            return None