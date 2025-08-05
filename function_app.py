# function_app.py

import logging
import json
import os
import azure.functions as func
#import redis
#import uuid
#from redis_client import redis_client


# 중요: func.FunctionApp() 인스턴스는 프로젝트 전체에서 단 한 번만 정의되어야 합니다.
app = func.FunctionApp()

logger = logging.getLogger(__name__)



# ==============================================================================
# 2. MaintenanceScheduler 함수 (Event Grid Trigger)
# 특정 조건(배터리, 상태)을 만족하는 이벤트에 대해 알림을 보냅니다.
# ==============================================================================
@app.event_grid_trigger(arg_name="event")
def MaintenanceScheduler(event: func.EventGridEvent):
    logger.info('Python Event Grid trigger processed MaintenanceScheduler event.')
    
    try:
        event_data = event.get_json()
        robot_telemetry_body = event_data.get('body', {})

        if not robot_telemetry_body:
            logger.warning(f"Scheduler: Event body is empty or malformed: {event_data}")
            return

        device_id = robot_telemetry_body.get('deviceId', 'N/A')
        battery_level = robot_telemetry_body.get('batteryLevel')
        current_status = robot_telemetry_body.get('currentStatus', 'N/A')
        ttimestamp = robot_telemetry_body.get('ttimestamp', 'N/A')
        
        alert_triggered = False
        alert_reason = []

        if battery_level is not None and battery_level < 20:
            alert_triggered = True
            alert_reason.append(f"배터리 잔량 {battery_level}% 미만")

        if current_status.lower() == 'error':
            alert_triggered = True
            alert_reason.append(f"현재 상태 '{current_status}' (에러)")

        if alert_triggered:
            alert_subject = f"[긴급 알림] 로봇 {device_id} - 유지보수 필요!"
            alert_content = (
                f"로봇 ID: {device_id} (시간: {ttimestamp})\n"
                f"이유: {', '.join(alert_reason)}\n"
                f"현재 배터리: {battery_level}%, 상태: {current_status}\n\n"
                "자세한 내용은 호수 수질 관리 시스템을 확인해주세요."
            )
            
            logger.critical(f"Scheduler: Alert triggered for robot {device_id}: {alert_content}")
        else:
            logger.info(f"Scheduler: No alert triggered for robot {device_id} (Battery: {battery_level}%, Status: {current_status})")

    except json.JSONDecodeError:
        logger.error(f"Scheduler: Could not decode JSON from Event Grid event: {event.get_body()}")
    except Exception as e:
        logger.error(f"Scheduler: Error processing Event Grid event: {e}", exc_info=True)


@func.function_app.http(route="redis-set")
def redis_set(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse("Redis key set successfully.")

@func.function_app.http(route="redis-get")
def redis_get(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse(f"Value from Redis: {value}")
