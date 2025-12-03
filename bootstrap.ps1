# Bootstrap Document Translator
# This script starts the backend and frontend services.

Write-Host "Bootstrapping Document Translator..." -ForegroundColor Green

# Check for uv
if (-not (Get-Command "uv" -ErrorAction SilentlyContinue)) {
    Write-Error "uv is not installed. Please install it first: https://github.com/astral-sh/uv"
    exit 1
}

# 1. Backend Setup & Run
Write-Host "Starting Backend..." -ForegroundColor Cyan
if (Test-Path "backend") {
    # Ensure dependencies are synced
    Write-Host "Syncing backend dependencies..."
    Start-Process -FilePath "uv" -ArgumentList "sync" -WorkingDirectory "backend" -Wait -NoNewWindow
    
    # Start the server
    Write-Host "Launching Backend Server..."
    Start-Process -FilePath "uv" -ArgumentList "run --project backend uvicorn backend.api.main:app --reload --port 8001"
} else {
    Write-Error "Backend directory not found!"
}

# 2. Frontend Setup & Run
Write-Host "Starting Frontend..." -ForegroundColor Cyan
if (Test-Path "frontend") {
    $FrontendCmd = "npm"
    $FrontendRunArgs = "run dev"
    
    if (Get-Command "bun" -ErrorAction SilentlyContinue) {
        Write-Host "Using Bun for frontend..."
        $FrontendCmd = "bun"
        
        # Install dependencies
        Write-Host "Installing frontend dependencies..."
        Start-Process -FilePath "bun" -ArgumentList "install" -WorkingDirectory "frontend" -Wait -NoNewWindow
    } else {
        Write-Host "Using npm for frontend..."
        # Install dependencies
        Write-Host "Installing frontend dependencies..."
        Start-Process -FilePath "npm" -ArgumentList "install" -WorkingDirectory "frontend" -Wait -NoNewWindow
    }

    # Start the server
    Write-Host "Launching Frontend Server..."
    Start-Process -FilePath $FrontendCmd -ArgumentList $FrontendRunArgs -WorkingDirectory "frontend"
} else {
    Write-Error "Frontend directory not found!"
}

Write-Host "Bootstrap complete. Services are starting in separate windows." -ForegroundColor Green
