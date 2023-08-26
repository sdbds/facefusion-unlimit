$execution_provider="cuda"
$execution_thread_count=8
$temp_frame_quality=0
$output_video_quality=0

Set-Location $PSScriptRoot
.\venv\Scripts\activate

$Env:HF_HOME = "./huggingface"

python.exe run.py `
--frame-processor face_swapper face_enhancer `
--execution-provider=$execution_provider `
--execution-thread-count=$execution_thread_count `
--temp-frame-quality=$temp_frame_quality `
--output-video-quality=$output_video_quality
